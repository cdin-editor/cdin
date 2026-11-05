#include "cdin/backend.h"
#include "cdin/backend_protocol.h"
#include "cdin/log.h"
#include "cdin/frontend/core/protocol/client.h"
#include "cdin/frontend/core/session/session.h"
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define CDIN_SMOKE_FRAME_BYTES CDIN_FRONTEND_PROTOCOL_DEFAULT_MAX_FRAME_BYTES
#define CDIN_SMOKE_FRAME_CAPACITY (CDIN_SMOKE_FRAME_BYTES + CDIN_FRONTEND_PROTOCOL_FRAME_PREFIX_BYTES)

typedef struct cdin_inproc_transport {
    cdin_backend *backend;
    cdin_backend_frontend *frontend;
    uint8_t *incoming;
    size_t incoming_length;
    size_t incoming_expected;
    uint8_t *outgoing;
    size_t outgoing_length;
    size_t outgoing_offset;
    uint64_t outgoing_flush_sequence;
    size_t outgoing_message_index;
    cdin_frontend_protocol_message_type outgoing_message_type;
    int outgoing_waiting_ack;
} cdin_inproc_transport;

static int process_inbound_frame(cdin_inproc_transport *transport)
{
    cdin_backend_status status;
    cdin_frontend_protocol_message_view inbound;
    size_t processed = 0u;
    cdin_frontend_protocol_status protocol_status;
    protocol_status = cdin_frontend_protocol_decode_frame(
        transport->incoming, transport->incoming_expected, &inbound, CDIN_SMOKE_FRAME_BYTES);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) return -1;
    if (transport->outgoing_waiting_ack && inbound.type != CDIN_FRONTEND_PROTOCOL_ACK) return -1;
    status = cdin_backend_frontend_receive(
        transport->frontend, transport->incoming, transport->incoming_expected);
    if (status != CDIN_BACKEND_OK) return -1;
    status = cdin_backend_pump(transport->backend, 64u, &processed);
    if (status != CDIN_BACKEND_OK) return -1;
    if (transport->outgoing_waiting_ack) {
        transport->outgoing_waiting_ack = 0;
        transport->outgoing_message_index = 0u;
    }
    return 0;
}

static ptrdiff_t cdin_inproc_write(void *context, const uint8_t *bytes, size_t length)
{
    cdin_inproc_transport *transport = (cdin_inproc_transport *)context;
    size_t consumed = 0u;
    if (transport == NULL || (bytes == NULL && length != 0u)) return -1;

    while (consumed < length) {
        size_t target = transport->incoming_expected == 0u
            ? 4u : transport->incoming_expected;
        size_t available;
        size_t amount;
        if (transport->incoming_length >= target) return -1;
        available = target - transport->incoming_length;
        amount = length - consumed;
        if (amount > available) amount = available;
        memcpy(transport->incoming + transport->incoming_length, bytes + consumed, amount);
        transport->incoming_length += amount;
        consumed += amount;

        if (transport->incoming_expected == 0u && transport->incoming_length == 4u) {
            size_t body_length =
                ((size_t)transport->incoming[0] << 24) |
                ((size_t)transport->incoming[1] << 16) |
                ((size_t)transport->incoming[2] << 8) |
                (size_t)transport->incoming[3];
            if (body_length == 0u || body_length > CDIN_SMOKE_FRAME_BYTES) return -1;
            transport->incoming_expected =
                body_length + CDIN_FRONTEND_PROTOCOL_FRAME_PREFIX_BYTES;
        }
        if (transport->incoming_expected != 0u &&
            transport->incoming_length == transport->incoming_expected) {
            if (process_inbound_frame(transport) != 0) return -1;
            transport->incoming_length = 0u;
            transport->incoming_expected = 0u;
        }
    }
    return (ptrdiff_t)length;
}

static ptrdiff_t cdin_inproc_read(void *context, uint8_t *buffer, size_t length)
{
    cdin_inproc_transport *transport = (cdin_inproc_transport *)context;
    cdin_backend_message message;
    cdin_backend_status status;
    size_t pending;
    size_t available;
    size_t amount;
    if (transport == NULL || (buffer == NULL && length != 0u)) return -1;
    if (length == 0u || transport->outgoing_waiting_ack) return 0;

    if (transport->outgoing_offset == transport->outgoing_length) {
        transport->outgoing_offset = 0u;
        transport->outgoing_length = 0u;
        pending = cdin_backend_frontend_pending(transport->frontend);
        if (transport->outgoing_message_index >= pending) return 0;
        status = cdin_backend_frontend_message_at(
            transport->frontend, transport->outgoing_message_index, &message);
        if (status != CDIN_BACKEND_OK) return -1;
        transport->outgoing_flush_sequence = message.flush_sequence;
        transport->outgoing_message_type = (cdin_frontend_protocol_message_type)message.type;
        status = cdin_backend_frontend_encode_message(
            transport->frontend, transport->outgoing_message_index, transport->outgoing,
            CDIN_SMOKE_FRAME_CAPACITY, &transport->outgoing_length);
        if (status != CDIN_BACKEND_OK) return -1;
    }

    available = transport->outgoing_length - transport->outgoing_offset;
    amount = length < available ? length : available;
    memcpy(buffer, transport->outgoing + transport->outgoing_offset, amount);
    transport->outgoing_offset += amount;
    if (transport->outgoing_offset == transport->outgoing_length) {
        if (transport->outgoing_message_type == CDIN_FRONTEND_PROTOCOL_UI_FLUSH) {
            if (transport->outgoing_flush_sequence == 0u) return -1;
            transport->outgoing_waiting_ack = 1;
        } else if (transport->outgoing_flush_sequence == 0u) {
            status = cdin_backend_frontend_consume_control_message(transport->frontend);
            if (status != CDIN_BACKEND_OK) return -1;
            transport->outgoing_message_index = 0u;
        } else {
            transport->outgoing_message_index++;
        }
        transport->outgoing_offset = 0u;
        transport->outgoing_length = 0u;
    }
    return (ptrdiff_t)amount;
}

int cdin_frontend_backend_smoke(cdin_backend *backend, cdin_log *log)
{
    cdin_inproc_transport transport;
    cdin_frontend_protocol_io io;
    cdin_frontend_client client;
    cdin_frontend_session session;
    cdin_frontend_protocol_message_view message;
    uint8_t *client_buffer = NULL;
    cdin_backend_status backend_status;
    cdin_frontend_protocol_status protocol_status;
    size_t snapshot_messages;
    size_t index;
    size_t options_count = 0u, styles_count = 0u, layout_count = 0u, flush_count = 0u;
    uint64_t last_wire_sequence = 0u;
    uint64_t snapshot_revision = 0u;
    int result = -1;

    if (backend == NULL || log == NULL || log->logger == NULL) return -1;
    memset(&transport, 0, sizeof(transport));
    transport.backend = backend;
    transport.incoming = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    transport.outgoing = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    client_buffer = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    if (transport.incoming == NULL || transport.outgoing == NULL || client_buffer == NULL) {
        MMLLOG_ERROR(log->logger, "Frontend protocol smoke could not allocate frame buffers");
        goto cleanup;
    }

    backend_status = cdin_backend_frontend_open(backend, &transport.frontend);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend frontend open failed: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }

    io.context = &transport;
    io.read = cdin_inproc_read;
    io.write = cdin_inproc_write;
    protocol_status = cdin_frontend_client_init(
        &client, &io, client_buffer, CDIN_SMOKE_FRAME_CAPACITY,
        CDIN_SMOKE_FRAME_BYTES);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend client init failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }

    cdin_frontend_session_init(&session, &client, NULL, "cdin-headless-smoke");
    protocol_status = cdin_frontend_session_set_capabilities(&session, 0u);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend capability setup failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }
    protocol_status = cdin_frontend_session_hello(&session);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend HELLO failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }
    protocol_status = cdin_frontend_session_receive(&session, &message);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK ||
        message.type != CDIN_FRONTEND_PROTOCOL_HELLO_ACK ||
        session.client_id == 0u || session.session_id == 0u ||
        session.state != CDIN_FRONTEND_SESSION_NEGOTIATED) {
        MMLLOG_ERROR(log->logger, "Frontend HELLO_ACK validation failed");
        goto cleanup;
    }

    protocol_status = cdin_frontend_session_attach(&session, "cdin-smoke-view", "cells", 80u, 24u);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend ATTACH send failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }
    snapshot_messages = cdin_backend_frontend_pending(transport.frontend);
    if (snapshot_messages < 2u) {
        MMLLOG_ERROR(log->logger, "Backend did not queue an initial UI snapshot after ATTACH");
        goto cleanup;
    }
    for (index = 0u; index < snapshot_messages; index++) {
        uint64_t sequence;
        protocol_status = cdin_frontend_session_receive(&session, &message);
        if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK ||
            message.sequence <= last_wire_sequence) {
            MMLLOG_ERROR(log->logger, "Frontend snapshot frame/order validation failed");
            goto cleanup;
        }
        last_wire_sequence = message.sequence;
        switch (message.type) {
        case CDIN_FRONTEND_PROTOCOL_UI_OPTIONS: options_count++; break;
        case CDIN_FRONTEND_PROTOCOL_UI_STYLE_TABLE: styles_count++; break;
        case CDIN_FRONTEND_PROTOCOL_UI_LAYOUT: layout_count++; break;
        case CDIN_FRONTEND_PROTOCOL_UI_FLUSH: {
            char scope[16];
            size_t scope_length = 0u;
            if (cdin_frontend_protocol_payload_get_text(
                    message.payload, message.payload_length, "scope",
                    scope, sizeof(scope), &scope_length) != CDIN_FRONTEND_PROTOCOL_OK ||
                scope_length != 8u || memcmp(scope, "snapshot", 8u) != 0 ||
                cdin_frontend_protocol_payload_get_uint(
                    message.payload, message.payload_length, "revision",
                    &snapshot_revision) != CDIN_FRONTEND_PROTOCOL_OK ||
                cdin_frontend_protocol_payload_get_uint(
                    message.payload, message.payload_length, "sequence",
                    &sequence) != CDIN_FRONTEND_PROTOCOL_OK ||
                sequence == 0u || sequence != session.last_flush_sequence) {
                MMLLOG_ERROR(log->logger, "Initial UI snapshot flush marker is invalid");
                goto cleanup;
            }
            flush_count++;
            if (index + 1u != snapshot_messages ||
                cdin_backend_frontend_pending(transport.frontend) == 0u) {
                MMLLOG_ERROR(log->logger, "Snapshot flush was not the final queued message");
                goto cleanup;
            }
            protocol_status = cdin_frontend_session_ack(&session, sequence);
            if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
                MMLLOG_ERROR(log->logger, "Initial UI snapshot ACK send failed: %s",
                             cdin_frontend_protocol_status_name(protocol_status));
                goto cleanup;
            }
            break;
        }
        default:
            break;
        }
    }
    if (options_count != 1u || styles_count != 1u || layout_count != 1u ||
        flush_count != 1u ||
        session.state != CDIN_FRONTEND_SESSION_ATTACHED ||
        cdin_backend_frontend_pending(transport.frontend) != 0u) {
        MMLLOG_ERROR(log->logger,
                     "Initial UI snapshot incomplete options=%llu styles=%llu layout=%llu flush=%llu pending=%llu",
                     (unsigned long long)options_count, (unsigned long long)styles_count,
                     (unsigned long long)layout_count, (unsigned long long)flush_count,
                     (unsigned long long)cdin_backend_frontend_pending(transport.frontend));
        goto cleanup;
    }

    protocol_status = cdin_frontend_session_resize(&session, 100u, 30u);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend resize propagation failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }

    MMLLOG_INFO(log->logger,
                "Frontend attach smoke passed: snapshot revision=%llu messages=%llu ordered flush/ACK and resize",
                (unsigned long long)snapshot_revision,
                (unsigned long long)snapshot_messages);
    result = 0;

cleanup:
    if (transport.frontend != NULL) {
        backend_status = cdin_backend_frontend_close(transport.frontend);
        if (backend_status != CDIN_BACKEND_OK) {
            MMLLOG_ERROR(log->logger, "Backend frontend close failed: %s",
                         cdin_backend_status_name(backend_status));
            result = -1;
        }
    }
    free(client_buffer);
    free(transport.outgoing);
    free(transport.incoming);
    return result;
}
