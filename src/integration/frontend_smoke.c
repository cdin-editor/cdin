#include "cdin/backend.h"
#include "cdin/backend_protocol.h"
#include "cdin/log.h"
#include "cdin/frontend/core/protocol/client.h"
#include "cdin/frontend/core/session/session.h"
#include "cdin/frontend/ui/tui/session.h"
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define CDIN_SMOKE_FRAME_BYTES CDIN_FRONTEND_PROTOCOL_DEFAULT_MAX_FRAME_BYTES
#define CDIN_SMOKE_FRAME_CAPACITY (CDIN_SMOKE_FRAME_BYTES + CDIN_FRONTEND_PROTOCOL_FRAME_PREFIX_BYTES)
#define CDIN_SMOKE_MAX_MESSAGES 512u

typedef struct cdin_inproc_transport {
    cdin_backend *backend;
    cdin_backend_frontend *frontend;
    uint8_t *incoming;
    size_t incoming_length;
    size_t incoming_expected;
    uint8_t *outgoing;
    size_t outgoing_length;
    size_t outgoing_offset;
    size_t outgoing_index;
    uint64_t outgoing_flush_sequence;
} cdin_inproc_transport;

static int count_acked_messages(cdin_inproc_transport *transport,
                                uint64_t acknowledged_sequence,
                                size_t *out_count)
{
    size_t pending;
    size_t i;
    size_t count = 0u;
    pending = cdin_backend_frontend_pending(transport->frontend);
    for (i = 0u; i < pending; i++) {
        cdin_backend_message message;
        cdin_backend_status status =
            cdin_backend_frontend_message_at(transport->frontend, i, &message);
        if (status != CDIN_BACKEND_OK) return -1;
        if (message.flush_sequence != 0u &&
            message.flush_sequence <= acknowledged_sequence) {
            count++;
        }
    }
    *out_count = count;
    return 0;
}

static int process_inbound_frame(cdin_inproc_transport *transport)
{
    cdin_frontend_protocol_message_view view;
    cdin_frontend_protocol_status decode_status;
    cdin_backend_status backend_status;
    size_t removed = 0u;
    size_t processed = 0u;
    uint64_t acknowledged_sequence = 0u;

    decode_status = cdin_frontend_protocol_decode_frame(
        transport->incoming, transport->incoming_expected, &view,
        CDIN_SMOKE_FRAME_BYTES);
    if (decode_status != CDIN_FRONTEND_PROTOCOL_OK) return -1;

    if (view.type == CDIN_FRONTEND_PROTOCOL_ACK) {
        if (cdin_frontend_protocol_payload_get_uint(
                view.payload, view.payload_length, "sequence",
                &acknowledged_sequence) != CDIN_FRONTEND_PROTOCOL_OK ||
            count_acked_messages(transport, acknowledged_sequence, &removed) != 0) {
            return -1;
        }
        if (transport->outgoing_length != transport->outgoing_offset) return -1;
    }

    backend_status = cdin_backend_frontend_receive(
        transport->frontend, transport->incoming, transport->incoming_expected);
    if (backend_status != CDIN_BACKEND_OK) return -1;

    backend_status = cdin_backend_pump(transport->backend, 64u, &processed);
    if (backend_status != CDIN_BACKEND_OK) return -1;

    if (removed >= transport->outgoing_index) transport->outgoing_index = 0u;
    else transport->outgoing_index -= removed;
    return 0;
}

static ptrdiff_t cdin_inproc_write(void *context, const uint8_t *bytes, size_t length)
{
    cdin_inproc_transport *transport = (cdin_inproc_transport *)context;
    size_t consumed = 0u;
    if (transport == NULL || (bytes == NULL && length != 0u)) return -1;

    while (consumed < length) {
        size_t target;
        size_t available;
        size_t amount;

        if (transport->incoming_expected == 0u) target = 4u;
        else target = transport->incoming_expected;

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
    cdin_backend_status backend_status;
    size_t pending;
    size_t available;
    size_t amount;

    if (transport == NULL || (buffer == NULL && length != 0u)) return -1;
    if (length == 0u) return 0;

    if (transport->outgoing_offset == transport->outgoing_length) {
        transport->outgoing_offset = 0u;
        transport->outgoing_length = 0u;
        pending = cdin_backend_frontend_pending(transport->frontend);
        if (transport->outgoing_index >= pending) return 0;

        backend_status = cdin_backend_frontend_message_at(
            transport->frontend, transport->outgoing_index, &message);
        if (backend_status != CDIN_BACKEND_OK) return -1;
        transport->outgoing_flush_sequence = message.flush_sequence;
        backend_status = cdin_backend_frontend_encode_message(
            transport->frontend, transport->outgoing_index,
            transport->outgoing, CDIN_SMOKE_FRAME_CAPACITY,
            &transport->outgoing_length);
        if (backend_status != CDIN_BACKEND_OK) return -1;
    }

    available = transport->outgoing_length - transport->outgoing_offset;
    amount = length < available ? length : available;
    memcpy(buffer, transport->outgoing + transport->outgoing_offset, amount);
    transport->outgoing_offset += amount;

    if (transport->outgoing_offset == transport->outgoing_length) {
        if (transport->outgoing_flush_sequence == 0u) {
            backend_status = cdin_backend_frontend_consume_control_message(
                transport->frontend);
            if (backend_status != CDIN_BACKEND_OK) return -1;
        } else {
            transport->outgoing_index++;
        }
        transport->outgoing_offset = 0u;
        transport->outgoing_length = 0u;
    }
    return (ptrdiff_t)amount;
}

static int cdin_inproc_has_message(const cdin_inproc_transport *transport)
{
    if (transport->outgoing_offset < transport->outgoing_length) return 1;
    return transport->outgoing_index <
           cdin_backend_frontend_pending(transport->frontend);
}

static int cdin_frontend_receive_snapshot(
    cdin_frontend_session *session,
    cdin_frontend_tui_model *model,
    cdin_inproc_transport *transport,
    cdin_log *log,
    size_t *out_flush_count)
{
    size_t iterations;
    for (iterations = 0u; iterations < CDIN_SMOKE_MAX_MESSAGES; iterations++) {
        cdin_frontend_protocol_message_view message;
        cdin_frontend_protocol_status protocol_status;
        cdin_frontend_tui_model_status model_status;
        int committed = 0;

        if (!cdin_inproc_has_message(transport)) return 0;
        protocol_status = cdin_frontend_session_receive(session, &message);
        if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
            MMLLOG_ERROR(log->logger, "Frontend receive failed: %s",
                         cdin_frontend_protocol_status_name(protocol_status));
            return -1;
        }
        if (message.type == CDIN_FRONTEND_PROTOCOL_HELLO_ACK ||
            message.type == CDIN_FRONTEND_PROTOCOL_DETACH_ACK) {
            MMLLOG_ERROR(log->logger, "Unexpected control reply during UI snapshot");
            return -1;
        }

        model_status = cdin_frontend_tui_receive(session, model, &message, &committed);
        if (model_status != CDIN_FRONTEND_TUI_MODEL_OK) {
            MMLLOG_ERROR(log->logger, "TUI model rejected Backend message: %d",
                         (int)model_status);
            return -1;
        }
        if (message.type == CDIN_FRONTEND_PROTOCOL_UI_FLUSH && committed) {
            (*out_flush_count)++;
        }
    }
    MMLLOG_ERROR(log->logger, "Frontend snapshot exceeded the bounded message budget");
    return -1;
}

int cdin_frontend_backend_smoke(cdin_backend *backend, cdin_log *log)
{
    cdin_inproc_transport transport;
    cdin_frontend_protocol_io io;
    cdin_frontend_client client;
    cdin_frontend_session session;
    cdin_frontend_tui_model *model = NULL;
    uint8_t *client_buffer = NULL;
    size_t flush_count = 0u;
    size_t processed = 0u;
    cdin_backend_status backend_status;
    cdin_frontend_protocol_status protocol_status;
    int result = -1;

    if (backend == NULL || log == NULL || log->logger == NULL) return -1;
    memset(&transport, 0, sizeof(transport));
    transport.backend = backend;
    transport.incoming = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    transport.outgoing = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    client_buffer = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    if (transport.incoming == NULL || transport.outgoing == NULL || client_buffer == NULL) {
        MMLLOG_ERROR(log->logger, "Frontend smoke could not allocate protocol frame buffers");
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

    if (!cdin_inproc_has_message(&transport)) {
        MMLLOG_ERROR(log->logger, "Backend did not queue HELLO_ACK");
        goto cleanup;
    }
    {
        cdin_frontend_protocol_message_view hello_ack;
        protocol_status = cdin_frontend_session_receive(&session, &hello_ack);
        if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK ||
            hello_ack.type != CDIN_FRONTEND_PROTOCOL_HELLO_ACK ||
            session.client_id == 0u || session.session_id == 0u) {
            MMLLOG_ERROR(log->logger, "Frontend HELLO_ACK validation failed");
            goto cleanup;
        }
    }

    model = cdin_frontend_tui_model_create("main", 24u, NULL);
    if (model == NULL) {
        MMLLOG_ERROR(log->logger, "TUI model creation failed");
        goto cleanup;
    }
    protocol_status = cdin_frontend_session_attach(&session, "main", "cells", 80u, 24u);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend ATTACH failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }

    if (cdin_frontend_receive_snapshot(&session, model, &transport, log, &flush_count) != 0) {
        goto cleanup;
    }
    if (session.state != CDIN_FRONTEND_SESSION_ATTACHED ||
        flush_count == 0u ||
        cdin_frontend_tui_model_revision(model) == 0u ||
        cdin_frontend_tui_model_last_flush(model) == 0u) {
        MMLLOG_ERROR(log->logger,
                     "Frontend attach did not commit a versioned UI snapshot");
        goto cleanup;
    }

    protocol_status = cdin_frontend_session_resize(&session, 100u, 30u);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend resize event failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }
    backend_status = cdin_backend_pump(backend, 64u, &processed);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend pump after resize failed: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }
    if (cdin_frontend_receive_snapshot(&session, model, &transport, log, &flush_count) != 0) {
        goto cleanup;
    }

    protocol_status = cdin_frontend_session_detach(&session);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend DETACH failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }
    if (!cdin_inproc_has_message(&transport)) {
        MMLLOG_ERROR(log->logger, "Backend did not queue DETACH_ACK");
        goto cleanup;
    }
    {
        cdin_frontend_protocol_message_view detach_ack;
        protocol_status = cdin_frontend_session_receive(&session, &detach_ack);
        if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK ||
            detach_ack.type != CDIN_FRONTEND_PROTOCOL_DETACH_ACK ||
            session.state != CDIN_FRONTEND_SESSION_DETACHED) {
            MMLLOG_ERROR(log->logger, "Frontend DETACH_ACK validation failed");
            goto cleanup;
        }
    }

    MMLLOG_INFO(log->logger,
                "Frontend protocol smoke passed: HELLO, ATTACH, %zu committed UI flushes, resize, DETACH",
                flush_count);
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
    cdin_frontend_tui_model_destroy(model);
    free(client_buffer);
    free(transport.outgoing);
    free(transport.incoming);
    return result;
}
