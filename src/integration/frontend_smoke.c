#include "cdin/backend.h"
#include "cdin/backend_protocol.h"
#include "cdin/log.h"
#include "cdin/frontend/core/protocol/client.h"
#include "cdin/frontend/core/session/session.h"
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <process.h>
#define CDIN_SMOKE_PROCESS_ID() ((unsigned long)_getpid())
#else
#include <unistd.h>
#define CDIN_SMOKE_PROCESS_ID() ((unsigned long)getpid())
#endif

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


/* Drain exactly one atomic Backend-to-Frontend flush group. Every group is
 * acknowledged through the public Frontend session API before the next event
 * is sent, so the smoke test exercises the real queue/ACK backpressure path. */
static int drain_frontend_batch(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    const char *expected_scope,
    char *out_view_id,
    size_t out_view_id_capacity,
    uint64_t *out_version,
    uint8_t *out_line_bytes,
    size_t out_line_capacity,
    size_t *out_line_length)
{
    size_t attempt;
    int saw_flush = 0;
    int saw_lines = 0;
    if (transport == NULL || session == NULL || expected_scope == NULL ||
        cdin_backend_frontend_pending(transport->frontend) == 0u) return -1;
    if (out_view_id != NULL && out_view_id_capacity != 0u) out_view_id[0] = '\0';
    if (out_version != NULL) *out_version = 0u;
    if (out_line_length != NULL) *out_line_length = 0u;

    for (attempt = 0u; attempt < 256u; attempt++) {
        cdin_frontend_protocol_message_view message;
        cdin_frontend_protocol_status protocol_status =
            cdin_frontend_session_receive(session, &message);
        if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) return -1;

        if (message.type == CDIN_FRONTEND_PROTOCOL_ERROR) return -1;

        if (message.type == CDIN_FRONTEND_PROTOCOL_VIEW_INVALIDATE) {
            size_t view_id_length = 0u;
            if (out_view_id != NULL && out_view_id_capacity != 0u &&
                cdin_frontend_protocol_payload_get_text(
                    message.payload, message.payload_length, "view_id",
                    out_view_id, out_view_id_capacity, &view_id_length) != CDIN_FRONTEND_PROTOCOL_OK) {
                return -1;
            }
            if (out_version != NULL &&
                cdin_frontend_protocol_payload_get_uint(
                    message.payload, message.payload_length, "version",
                    out_version) != CDIN_FRONTEND_PROTOCOL_OK) {
                return -1;
            }
        } else if (message.type == CDIN_FRONTEND_PROTOCOL_VIEW_LINES) {
            const uint8_t *array = NULL;
            size_t array_length = 0u;
            size_t line_count = 0u;
            size_t line_index;
            if (out_line_bytes == NULL || out_line_length == NULL ||
                cdin_frontend_protocol_payload_get_raw(
                    message.payload, message.payload_length, "lines",
                    &array, &array_length) != CDIN_FRONTEND_PROTOCOL_OK ||
                cdin_frontend_protocol_array_count(array, array_length, &line_count) !=
                    CDIN_FRONTEND_PROTOCOL_OK) {
                return -1;
            }
            for (line_index = 0u; line_index < line_count; line_index++) {
                const uint8_t *line_map = NULL;
                size_t line_map_length = 0u;
                const uint8_t *bytes = NULL;
                size_t bytes_length = 0u;
                if (cdin_frontend_protocol_array_get_raw(
                        array, array_length, line_index,
                        &line_map, &line_map_length) != CDIN_FRONTEND_PROTOCOL_OK ||
                    cdin_frontend_protocol_payload_get_bytes(
                        line_map, line_map_length, "bytes", &bytes,
                        &bytes_length) != CDIN_FRONTEND_PROTOCOL_OK ||
                    bytes_length > out_line_capacity - *out_line_length) {
                    return -1;
                }
                if (bytes_length != 0u) {
                    memcpy(out_line_bytes + *out_line_length, bytes, bytes_length);
                    *out_line_length += bytes_length;
                }
            }
            saw_lines = 1;
        } else if (message.type == CDIN_FRONTEND_PROTOCOL_UI_FLUSH) {
            char scope[16];
            size_t scope_length = 0u;
            uint64_t flush_sequence = 0u;
            if (cdin_frontend_protocol_payload_get_text(
                    message.payload, message.payload_length, "scope",
                    scope, sizeof(scope), &scope_length) != CDIN_FRONTEND_PROTOCOL_OK ||
                strcmp(scope, expected_scope) != 0 ||
                cdin_frontend_protocol_payload_get_uint(
                    message.payload, message.payload_length, "sequence",
                    &flush_sequence) != CDIN_FRONTEND_PROTOCOL_OK ||
                flush_sequence == 0u ||
                cdin_frontend_session_ack(session, flush_sequence) !=
                    CDIN_FRONTEND_PROTOCOL_OK) {
                return -1;
            }
            saw_flush = 1;
            if (cdin_backend_frontend_pending(transport->frontend) == 0u) {
                if (out_line_bytes != NULL && !saw_lines) return -1;
                return 0;
            }
        }
    }
    (void)saw_flush;
    return -1;
}

static int send_command_and_drain(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    const char *name,
    const char *path,
    char *view_id,
    size_t view_id_capacity,
    uint64_t *version)
{
    if (cdin_frontend_session_request_command(session, name, path) !=
        CDIN_FRONTEND_PROTOCOL_OK) return -1;
    return drain_frontend_batch(transport, session, "snapshot",
                                view_id, view_id_capacity, version,
                                NULL, 0u, NULL);
}

static int send_key_and_drain(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    const char *key,
    uint32_t modifiers,
    uint64_t *version)
{
    if (cdin_frontend_session_send_key(session, key, modifiers, "press") !=
        CDIN_FRONTEND_PROTOCOL_OK) return -1;
    return drain_frontend_batch(transport, session, "snapshot",
                                NULL, 0u, version, NULL, 0u, NULL);
}

static int verify_saved_bytes(const char *path, const uint8_t *expected,
                              size_t expected_length)
{
    FILE *file = fopen(path, "rb");
    uint8_t bytes[64];
    size_t count;
    int equal;
    if (file == NULL) return 0;
    count = fread(bytes, 1u, sizeof(bytes), file);
    equal = count == expected_length &&
        (count == 0u || memcmp(bytes, expected, count) == 0) &&
        fgetc(file) == EOF && !ferror(file);
    if (fclose(file) != 0) equal = 0;
    return equal;
}

/*
 * Exercise the product path across Frontend Protocol -> Backend owner-thread
 * queue -> Runtime command/keymap dispatch -> Kernel document -> Backend
 * filesystem. The final bytes are independently read from the saved file and
 * then fetched again through the public version-pinned view.request_lines API.
 */
static int cdin_frontend_document_smoke(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    cdin_log *log)
{
    static const uint8_t paste_bytes[] = { 0x00u, 0xffu, '\r', '\n', 'B' };
    static const uint8_t expected_bytes[] = { 'A', 0x00u, 0xffu, '\r', '\n', 'B' };
    uint8_t returned_bytes[64];
    char path[128];
    char view_id[64];
    uint64_t version = 0u;
    size_t returned_length = 0u;
    unsigned long process_id = CDIN_SMOKE_PROCESS_ID();
    int result = -1;

    (void)snprintf(path, sizeof(path), "cdin-smoke-document-%lu.bin", process_id);
    (void)remove(path);
    view_id[0] = '\0';

    if (send_command_and_drain(transport, session, "document.new",
                               path, view_id, sizeof(view_id), &version) != 0 ||
        view_id[0] == '\0') {
        MMLLOG_ERROR(log->logger, "Runtime document.new did not publish a focused view");
        goto cleanup;
    }

    if (cdin_frontend_session_send_text(session, (const uint8_t *)"A", 1u) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        drain_frontend_batch(transport, session, "snapshot",
                             NULL, 0u, &version, NULL, 0u, NULL) != 0) {
        MMLLOG_ERROR(log->logger, "Frontend input.text did not reach Runtime");
        goto cleanup;
    }
    if (cdin_frontend_session_send_paste(session, paste_bytes, sizeof(paste_bytes)) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        drain_frontend_batch(transport, session, "snapshot",
                             NULL, 0u, &version, NULL, 0u, NULL) != 0) {
        MMLLOG_ERROR(log->logger, "Frontend input.paste did not reach Runtime");
        goto cleanup;
    }

    if (send_key_and_drain(transport, session, "z", CDIN_FRONTEND_MOD_CTRL, &version) != 0 ||
        send_key_and_drain(transport, session, "z", CDIN_FRONTEND_MOD_CTRL, &version) != 0 ||
        send_key_and_drain(transport, session, "z",
            CDIN_FRONTEND_MOD_CTRL | CDIN_FRONTEND_MOD_SHIFT, &version) != 0 ||
        send_key_and_drain(transport, session, "z",
            CDIN_FRONTEND_MOD_CTRL | CDIN_FRONTEND_MOD_SHIFT, &version) != 0) {
        MMLLOG_ERROR(log->logger, "Runtime undo/redo keymap dispatch failed");
        goto cleanup;
    }

    if (cdin_frontend_session_request_lines(session, view_id, 0u, 2u, version) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        drain_frontend_batch(transport, session, "response",
                             NULL, 0u, NULL, returned_bytes, sizeof(returned_bytes),
                             &returned_length) != 0 ||
        returned_length != sizeof(expected_bytes) ||
        memcmp(returned_bytes, expected_bytes, sizeof(expected_bytes)) != 0) {
        MMLLOG_ERROR(log->logger,
                     "Kernel line-window bytes differ after text/paste/undo/redo (returned=%llu)",
                     (unsigned long long)returned_length);
        goto cleanup;
    }

    if (send_key_and_drain(transport, session, "s", CDIN_FRONTEND_MOD_CTRL, &version) != 0 ||
        !verify_saved_bytes(path, expected_bytes, sizeof(expected_bytes))) {
        MMLLOG_ERROR(log->logger, "Runtime Ctrl+S did not atomically save exact document bytes");
        goto cleanup;
    }

    if (send_command_and_drain(transport, session, "document.close",
                               NULL, NULL, 0u, NULL) != 0) {
        MMLLOG_ERROR(log->logger, "Runtime document.close failed");
        goto cleanup;
    }
    view_id[0] = '\0';
    version = 0u;
    if (send_command_and_drain(transport, session, "document.open",
                               path, view_id, sizeof(view_id), &version) != 0 ||
        view_id[0] == '\0') {
        MMLLOG_ERROR(log->logger, "Runtime document.open did not recreate a view");
        goto cleanup;
    }

    returned_length = 0u;
    memset(returned_bytes, 0, sizeof(returned_bytes));
    if (cdin_frontend_session_request_lines(session, view_id, 0u, 2u, version) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        drain_frontend_batch(transport, session, "response",
                             NULL, 0u, NULL, returned_bytes, sizeof(returned_bytes),
                             &returned_length) != 0 ||
        returned_length != sizeof(expected_bytes) ||
        memcmp(returned_bytes, expected_bytes, sizeof(expected_bytes)) != 0) {
        MMLLOG_ERROR(log->logger,
                     "Reopened document bytes differ from the saved Kernel snapshot");
        goto cleanup;
    }

    if (send_command_and_drain(transport, session, "document.close",
                               NULL, NULL, 0u, NULL) != 0) {
        MMLLOG_ERROR(log->logger, "Runtime final document.close failed");
        goto cleanup;
    }
    MMLLOG_INFO(log->logger,
                "Frontend document smoke passed: text/paste, undo/redo, atomic save, close/open and %llu exact bytes",
                (unsigned long long)sizeof(expected_bytes));
    result = 0;

cleanup:
    (void)remove(path);
    return result;
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

    if (cdin_frontend_document_smoke(&transport, &session, log) != 0) {
        MMLLOG_ERROR(log->logger, "Frontend/Runtime/Kernel document workflow smoke failed");
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
