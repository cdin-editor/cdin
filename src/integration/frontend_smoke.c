#define _POSIX_C_SOURCE 200809L

#include "cdin/backend.h"
#include "cdin/backend_protocol.h"
#include "cdin/log.h"
#include "cdin/frontend/core/protocol/client.h"
#include "cdin/frontend/core/session/session.h"
#include "cdin/frontend/ui/tui/event_loop.h"
#include "cdin/frontend/ui/tui/input/parser.h"
#include "cdin/frontend/ui/tui/model.h"
#include "cdin/frontend/ui/tui/platform/terminal.h"
#include "cdin/frontend/ui/tui/session.h"
#include "cdin/frontend/ui/tui/tui.h"
#include "cdin/options.h"
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <direct.h>
#define CDIN_SMOKE_MKDIR(path) _mkdir(path)
#define CDIN_SMOKE_RMDIR(path) _rmdir(path)
#else
#include <sys/stat.h>
#define CDIN_SMOKE_MKDIR(path) mkdir((path), 0700)
#define CDIN_SMOKE_RMDIR(path) rmdir(path)
#endif
#ifndef _WIN32
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#endif
#ifdef _WIN32
#include <process.h>
#define CDIN_SMOKE_PROCESS_ID() ((unsigned long)_getpid())
#else
#include <unistd.h>
#define CDIN_SMOKE_PROCESS_ID() ((unsigned long)getpid())
#endif

#ifndef CDIN_DEFAULT_RUNTIME_ROOT
#define CDIN_DEFAULT_RUNTIME_ROOT "./lua"
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

static int write_fixture_file(const char *path, const uint8_t *bytes, size_t length)
{
    FILE *file;
    int result = 0;
    if (path == NULL || bytes == NULL || length == 0u) return -1;
    file = fopen(path, "wb");
    if (file == NULL) return -1;
    if (fwrite(bytes, 1u, length, file) != length || fflush(file) != 0) result = -1;
    if (fclose(file) != 0) result = -1;
    return result;
}

static int expect_protocol_error(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    const char *command,
    const char *path)
{
    cdin_frontend_protocol_message_view message;
    if (transport == NULL || session == NULL || command == NULL ||
        cdin_frontend_session_request_command(session, command, path) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        cdin_frontend_session_receive(session, &message) != CDIN_FRONTEND_PROTOCOL_OK ||
        message.type != CDIN_FRONTEND_PROTOCOL_ERROR) {
        return -1;
    }
    return cdin_backend_frontend_pending(transport->frontend) == 0u ? 0 : -1;
}

static int expect_key_protocol_error(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    const char *key,
    uint32_t modifiers)
{
    cdin_frontend_protocol_message_view message;
    if (transport == NULL || session == NULL || key == NULL ||
        cdin_frontend_session_send_key(session, key, modifiers, "press") !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        cdin_frontend_session_receive(session, &message) != CDIN_FRONTEND_PROTOCOL_OK ||
        message.type != CDIN_FRONTEND_PROTOCOL_ERROR) {
        return -1;
    }
    return cdin_backend_frontend_pending(transport->frontend) == 0u ? 0 : -1;
}

static int cdin_frontend_file_fixture_smoke(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    cdin_log *log)
{
    static const uint8_t bom_lf[] = {
        0xefu, 0xbbu, 0xbfu, 'a', 'l', 'p', 'h', 'a', '\n', 'b', 'e', 't', 'a', '\n'
    };
    static const uint8_t lf_only[] = {
        'o', 'n', 'e', '\n', 't', 'w', 'o', '\n', 't', 'h', 'r', 'e', 'e'
    };
    static const uint8_t mixed_eol[] = {
        0xefu, 0xbbu, 0xbfu, 'x', '\r', '\n', 'y', '\n', 'z', '\r', 'w'
    };
    static const struct {
        const char *name;
        const uint8_t *bytes;
        size_t length;
    } fixtures[] = {
        { "bom-lf", bom_lf, sizeof(bom_lf) },
        { "lf-only", lf_only, sizeof(lf_only) },
        { "mixed-eol", mixed_eol, sizeof(mixed_eol) },
    };
    uint8_t returned[64];
    char path[128];
    char view_id[64];
    uint64_t version;
    size_t returned_length;
    size_t index;
    unsigned long process_id = CDIN_SMOKE_PROCESS_ID();

    for (index = 0u; index < sizeof(fixtures) / sizeof(fixtures[0]); index++) {
        (void)snprintf(path, sizeof(path), "cdin-smoke-%s-%lu.bin",
                       fixtures[index].name, process_id);
        (void)remove(path);
        if (write_fixture_file(path, fixtures[index].bytes, fixtures[index].length) != 0) {
            MMLLOG_ERROR(log->logger, "Could not create %s fixture", fixtures[index].name);
            (void)remove(path);
            return -1;
        }
        view_id[0] = '\0';
        version = 0u;
        if (send_command_and_drain(transport, session, "document.open",
                                   path, view_id, sizeof(view_id), &version) != 0 ||
            view_id[0] == '\0') {
            MMLLOG_ERROR(log->logger, "Runtime could not open %s fixture", fixtures[index].name);
            (void)remove(path);
            return -1;
        }
        returned_length = 0u;
        memset(returned, 0, sizeof(returned));
        if (cdin_frontend_session_request_lines(session, view_id, 0u, 16u, version) !=
                CDIN_FRONTEND_PROTOCOL_OK ||
            drain_frontend_batch(transport, session, "response",
                                 NULL, 0u, NULL, returned, sizeof(returned),
                                 &returned_length) != 0 ||
            returned_length != fixtures[index].length ||
            memcmp(returned, fixtures[index].bytes, fixtures[index].length) != 0) {
            MMLLOG_ERROR(log->logger, "Byte-exact %s fixture read failed", fixtures[index].name);
            (void)remove(path);
            return -1;
        }
        if (send_key_and_drain(transport, session, "s",
                               CDIN_FRONTEND_MOD_CTRL, &version) != 0 ||
            !verify_saved_bytes(path, fixtures[index].bytes, fixtures[index].length)) {
            MMLLOG_ERROR(log->logger, "Byte-exact %s fixture save failed", fixtures[index].name);
            (void)remove(path);
            return -1;
        }
        if (send_command_and_drain(transport, session, "document.close",
                                   NULL, NULL, 0u, NULL) != 0) {
            MMLLOG_ERROR(log->logger, "Could not close %s fixture document", fixtures[index].name);
            (void)remove(path);
            return -1;
        }
        (void)remove(path);
    }
    MMLLOG_INFO(log->logger,
                "Frontend file fixture smoke passed: BOM, LF-only and mixed CRLF/LF/CR byte preservation");
    return 0;
}

static int cdin_frontend_filesystem_failure_smoke(
    cdin_inproc_transport *transport,
    cdin_frontend_session *session,
    cdin_log *log)
{
    static const uint8_t recovery_bytes[] = "recoverable";
    uint8_t returned[64];
    char missing_path[128];
    char directory_path[128];
    char recovery_path[128];
    char view_id[64];
    uint64_t version = 0u;
    size_t returned_length = 0u;
    unsigned long process_id = CDIN_SMOKE_PROCESS_ID();
    int directory_created = 0;

    (void)snprintf(missing_path, sizeof(missing_path),
                   "cdin-smoke-missing-%lu.bin", process_id);
    (void)snprintf(directory_path, sizeof(directory_path),
                   "cdin-smoke-save-target-%lu", process_id);
    (void)snprintf(recovery_path, sizeof(recovery_path),
                   "cdin-smoke-recovered-%lu.bin", process_id);
    (void)remove(missing_path);
    (void)remove(recovery_path);
    (void)CDIN_SMOKE_RMDIR(directory_path);

    if (expect_protocol_error(transport, session, "document.open", missing_path) != 0) {
        MMLLOG_ERROR(log->logger, "Missing-file open did not return a Protocol error");
        goto fail;
    }
    if (CDIN_SMOKE_MKDIR(directory_path) != 0) {
        MMLLOG_ERROR(log->logger, "Could not create directory save-failure fixture");
        goto fail;
    }
    directory_created = 1;
    view_id[0] = '\0';
    if (send_command_and_drain(transport, session, "document.new",
                               directory_path, view_id, sizeof(view_id), &version) != 0 ||
        view_id[0] == '\0' ||
        cdin_frontend_session_send_text(session, recovery_bytes,
                                        sizeof(recovery_bytes) - 1u) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        drain_frontend_batch(transport, session, "snapshot",
                             NULL, 0u, &version, NULL, 0u, NULL) != 0) {
        MMLLOG_ERROR(log->logger, "Could not prepare a path-backed document for failed save");
        goto fail;
    }
    if (expect_key_protocol_error(transport, session, "s",
                                  CDIN_FRONTEND_MOD_CTRL) != 0) {
        MMLLOG_ERROR(log->logger, "Saving to an existing directory did not return a Protocol error");
        goto fail;
    }

    /* A failed atomic commit must not damage the canonical in-memory bytes. */
    memset(returned, 0, sizeof(returned));
    returned_length = 0u;
    if (cdin_frontend_session_request_lines(session, view_id, 0u, 4u, version) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        drain_frontend_batch(transport, session, "response",
                             NULL, 0u, NULL, returned, sizeof(returned),
                             &returned_length) != 0 ||
        returned_length != sizeof(recovery_bytes) - 1u ||
        memcmp(returned, recovery_bytes, returned_length) != 0) {
        MMLLOG_ERROR(log->logger, "Failed save changed or invalidated the canonical document");
        goto fail;
    }
    if (send_command_and_drain(transport, session, "document.save",
                               recovery_path, NULL, 0u, NULL) != 0 ||
        !verify_saved_bytes(recovery_path, recovery_bytes, sizeof(recovery_bytes) - 1u)) {
        MMLLOG_ERROR(log->logger, "Document could not recover with a subsequent valid atomic save");
        goto fail;
    }
    if (send_command_and_drain(transport, session, "document.close",
                               NULL, NULL, 0u, NULL) != 0) {
        MMLLOG_ERROR(log->logger, "Could not close document after recovering failed save");
        goto fail;
    }
    (void)remove(recovery_path);
    (void)CDIN_SMOKE_RMDIR(directory_path);
    MMLLOG_INFO(log->logger,
                "Frontend filesystem failure smoke passed: missing read, failed atomic commit, intact bytes and successful recovery");
    return 0;

fail:
    (void)remove(recovery_path);
    if (directory_created) (void)CDIN_SMOKE_RMDIR(directory_path);
    return -1;
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
    if (cdin_frontend_file_fixture_smoke(&transport, &session, log) != 0 ||
        cdin_frontend_filesystem_failure_smoke(&transport, &session, log) != 0) {
        MMLLOG_ERROR(log->logger, "Frontend filesystem and byte-fixture smoke failed");
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


#ifndef _WIN32

typedef struct cdin_tui_context {
    cdin_backend *backend;
    cdin_inproc_transport transport;
    cdin_frontend_protocol_io io;
    cdin_frontend_client client;
    cdin_frontend_session session;
    cdin_frontend_terminal terminal;
    cdin_frontend_input_parser parser;
    cdin_frontend_tui_model *model;
    cdin_log *log;
    int wake_read;
    int wake_write;
    int terminal_opened;
    int session_initialized;
    int signals_installed;
    int shutdown_called;
    int backend_ready;
    int terminate_pending;
    int flush_escape;
    int parser_ready_pending;
    int terminal_buffer_only;
    uint32_t columns;
    uint32_t rows;
    char scratch_path[160];
    char title[192];
    char help_status[192];
    struct sigaction previous_winch;
    struct sigaction previous_term;
    struct sigaction previous_int;
    uint8_t *client_buffer;
} cdin_tui_context;

static volatile sig_atomic_t cdin_tui_signal_write_fd = -1;

static void cdin_tui_signal_handler(int signal_number)
{
    int descriptor = (int)cdin_tui_signal_write_fd;
    uint8_t code = signal_number == SIGWINCH ? (uint8_t)'R' : (uint8_t)'T';
    if (descriptor >= 0) {
        ssize_t written = write(descriptor, &code, 1u);
        (void)written;
    }
}

static int cdin_tui_set_nonblocking(int descriptor)
{
    int flags = fcntl(descriptor, F_GETFL, 0);
    int descriptor_flags;
    if (flags < 0 || fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) != 0) return -1;
    descriptor_flags = fcntl(descriptor, F_GETFD, 0);
    if (descriptor_flags < 0 ||
        fcntl(descriptor, F_SETFD, descriptor_flags | FD_CLOEXEC) != 0) return -1;
    return 0;
}

static int cdin_tui_create_wakeup_pipe(cdin_tui_context *context)
{
    int descriptors[2];
    if (context == NULL || pipe(descriptors) != 0) return -1;
    if (cdin_tui_set_nonblocking(descriptors[0]) != 0 ||
        cdin_tui_set_nonblocking(descriptors[1]) != 0) {
        (void)close(descriptors[0]);
        (void)close(descriptors[1]);
        return -1;
    }
    context->wake_read = descriptors[0];
    context->wake_write = descriptors[1];
    return 0;
}

static void cdin_tui_signal_write(cdin_tui_context *context, uint8_t code)
{
    ssize_t result;
    if (context == NULL || context->wake_write < 0) return;
    do {
        result = write(context->wake_write, &code, 1u);
    } while (result < 0 && errno == EINTR);
    /* EAGAIN means the pipe already contains a wakeup and is readable. */
}

static void cdin_tui_backend_wakeup(void *opaque)
{
    cdin_tui_context *context = (cdin_tui_context *)opaque;
    cdin_tui_signal_write(context, (uint8_t)'B');
}

static int cdin_tui_install_signal_handlers(cdin_tui_context *context)
{
    struct sigaction action;
    if (context == NULL || context->wake_write < 0) return -1;
    memset(&action, 0, sizeof(action));
    action.sa_handler = cdin_tui_signal_handler;
    if (sigemptyset(&action.sa_mask) != 0) return -1;
    cdin_tui_signal_write_fd = (sig_atomic_t)context->wake_write;
    if (sigaction(SIGWINCH, &action, &context->previous_winch) != 0) goto fail;
    if (sigaction(SIGTERM, &action, &context->previous_term) != 0) {
        (void)sigaction(SIGWINCH, &context->previous_winch, NULL);
        goto fail;
    }
    if (sigaction(SIGINT, &action, &context->previous_int) != 0) {
        (void)sigaction(SIGTERM, &context->previous_term, NULL);
        (void)sigaction(SIGWINCH, &context->previous_winch, NULL);
        goto fail;
    }
    context->signals_installed = 1;
    return 0;
fail:
    cdin_tui_signal_write_fd = -1;
    return -1;
}

static void cdin_tui_restore_signal_handlers(cdin_tui_context *context)
{
    if (context == NULL || !context->signals_installed) return;
    cdin_tui_signal_write_fd = -1;
    (void)sigaction(SIGINT, &context->previous_int, NULL);
    (void)sigaction(SIGTERM, &context->previous_term, NULL);
    (void)sigaction(SIGWINCH, &context->previous_winch, NULL);
    context->signals_installed = 0;
}

static int cdin_tui_wait(void *opaque, uint32_t requested_events,
                         int timeout_ms, uint32_t *out_ready_events)
{
    cdin_tui_context *context = (cdin_tui_context *)opaque;
    struct pollfd descriptors[2];
    int timeout = timeout_ms;
    int polled;
    uint32_t ready = 0u;
    if (context == NULL || out_ready_events == NULL ||
        (requested_events & CDIN_FRONTEND_TUI_EVENT_ALL) != CDIN_FRONTEND_TUI_EVENT_ALL) {
        return -1;
    }
    if (context->backend_ready) {
        ready |= CDIN_FRONTEND_TUI_EVENT_BACKEND_READABLE;
        context->backend_ready = 0;
    }
    if (context->parser_ready_pending) {
        context->parser_ready_pending = 0;
        context->terminal_buffer_only = 1;
        ready |= CDIN_FRONTEND_TUI_EVENT_TERMINAL_READABLE;
    }
    if (context->terminate_pending) {
        *out_ready_events = ready | CDIN_FRONTEND_TUI_EVENT_TERMINATE;
        return 0;
    }
    if (ready != 0u) {
        *out_ready_events = ready;
        return 0;
    }

    /* The Frontend parser needs one short ESC disambiguation window. All other
     * waits block indefinitely; there is no periodic polling or busy-wait. */
    if (context->parser.length == 1u && context->parser.bytes[0] == 0x1bu) timeout = 30;
    descriptors[0].fd = STDIN_FILENO;
    descriptors[0].events = POLLIN;
    descriptors[0].revents = 0;
    descriptors[1].fd = context->wake_read;
    descriptors[1].events = POLLIN;
    descriptors[1].revents = 0;
    do {
        polled = poll(descriptors, (nfds_t)2u, timeout);
    } while (polled < 0 && errno == EINTR);
    if (polled < 0) return -1;
    if (polled == 0) {
        context->flush_escape = 1;
        *out_ready_events = CDIN_FRONTEND_TUI_EVENT_TERMINAL_READABLE;
        return 0;
    }
    if ((descriptors[0].revents & (POLLIN | POLLHUP)) != 0) {
        ready |= CDIN_FRONTEND_TUI_EVENT_TERMINAL_READABLE;
    }
    if ((descriptors[0].revents & (POLLERR | POLLNVAL)) != 0) return -1;
    if ((descriptors[1].revents & POLLIN) != 0) {
        uint8_t bytes[128];
        ssize_t amount;
        for (;;) {
            amount = read(context->wake_read, bytes, sizeof(bytes));
            if (amount > 0) {
                ssize_t index;
                for (index = 0; index < amount; index++) {
                    switch (bytes[index]) {
                        case 'B': ready |= CDIN_FRONTEND_TUI_EVENT_BACKEND_READABLE; break;
                        case 'R': ready |= CDIN_FRONTEND_TUI_EVENT_RESIZE; break;
                        case 'T': ready |= CDIN_FRONTEND_TUI_EVENT_TERMINATE; break;
                        default: break;
                    }
                }
                continue;
            }
            if (amount < 0 && errno == EINTR) continue;
            if (amount < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) break;
            if (amount == 0) break;
            return -1;
        }
    }
    if ((descriptors[1].revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) return -1;
    *out_ready_events = ready;
    return ready != 0u ? 0 : -1;
}

static int cdin_tui_dispatch_input(cdin_tui_context *context,
                                   const cdin_frontend_input_event *event)
{
    cdin_frontend_protocol_status status;
    if (context == NULL || event == NULL) return -1;
    if (event->kind == CDIN_FRONTEND_INPUT_KEY &&
        (event->modifiers & CDIN_FRONTEND_MOD_CTRL) != 0u &&
        (strcmp(event->key, "c") == 0 || strcmp(event->key, "q") == 0)) {
        context->terminate_pending = 1;
        return 0;
    }
    status = cdin_frontend_tui_send_input(&context->session, event);
    if (status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(context->log->logger, "TUI input forwarding failed: %s",
                     cdin_frontend_protocol_status_name(status));
        return -1;
    }
    /* The in-process transport pumps synchronously; still schedule a Backend
     * drain so the common event loop applies and renders every resulting batch. */
    context->backend_ready = 1;
    return 0;
}

static int cdin_tui_parse_pending(cdin_tui_context *context, size_t budget,
                                  size_t *out_processed)
{
    size_t processed = 0u;
    while (processed < budget) {
        cdin_frontend_input_event event;
        int flush_escape = context->flush_escape;
        cdin_frontend_input_parser_status status;
        context->flush_escape = 0;
        status = cdin_frontend_input_parser_next(&context->parser, flush_escape, &event);
        if (status == CDIN_FRONTEND_INPUT_PARSER_EVENT) {
            if (cdin_tui_dispatch_input(context, &event) != 0) return -1;
            processed++;
            continue;
        }
        if (status == CDIN_FRONTEND_INPUT_PARSER_INVALID) continue;
        if (status == CDIN_FRONTEND_INPUT_PARSER_LIMIT_EXCEEDED) {
            MMLLOG_WARN(context->log->logger, "TUI discarded an oversized bracketed paste");
            continue;
        }
        if (status == CDIN_FRONTEND_INPUT_PARSER_NEED_MORE) break;
        return -1;
    }
    *out_processed = processed;
    return 0;
}

static cdin_frontend_tui_io_result cdin_tui_drain_terminal(
    void *opaque, size_t max_items, size_t *out_processed)
{
    cdin_tui_context *context = (cdin_tui_context *)opaque;
    uint8_t bytes[4096];
    ptrdiff_t amount;
    size_t processed = 0u;
    int was_escape_timeout;
    int buffer_only;
    if (context == NULL || out_processed == NULL || max_items == 0u) {
        return CDIN_FRONTEND_TUI_IO_FAILURE;
    }
    *out_processed = 0u;
    was_escape_timeout = context->flush_escape;
    buffer_only = context->terminal_buffer_only;
    context->terminal_buffer_only = 0;
    if (cdin_tui_parse_pending(context, max_items, &processed) != 0) {
        return CDIN_FRONTEND_TUI_IO_FAILURE;
    }
    if (processed != 0u) {
        if (processed == max_items && context->parser.length != 0u) {
            context->parser_ready_pending = 1;
        }
        *out_processed = processed;
        return CDIN_FRONTEND_TUI_DRAIN_PROGRESS;
    }
    /* Parser-buffer and ESC-timeout notifications do not authorize a read
     * from the blocking terminal adapter. Only poll readiness does. */
    if (was_escape_timeout || buffer_only) return CDIN_FRONTEND_TUI_DRAIN_AGAIN;

    amount = context->terminal.read(context->terminal.context, bytes, sizeof(bytes));
    if (amount == 0) return CDIN_FRONTEND_TUI_DRAIN_EOF;
#ifndef _WIN32
    if (amount < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
        return CDIN_FRONTEND_TUI_DRAIN_AGAIN;
    }
#endif
    if (amount < 0 || (size_t)amount > sizeof(bytes)) return CDIN_FRONTEND_TUI_IO_FAILURE;
    if (cdin_frontend_input_parser_feed(&context->parser, bytes, (size_t)amount) ==
        CDIN_FRONTEND_INPUT_PARSER_LIMIT_EXCEEDED) {
        cdin_frontend_input_parser_init(&context->parser);
        MMLLOG_WARN(context->log->logger, "TUI discarded terminal input after parser capacity was exceeded");
        return CDIN_FRONTEND_TUI_DRAIN_AGAIN;
    }
    if (cdin_tui_parse_pending(context, max_items, &processed) != 0) {
        return CDIN_FRONTEND_TUI_IO_FAILURE;
    }
    if (processed == 0u) return CDIN_FRONTEND_TUI_DRAIN_AGAIN;
    if (processed == max_items && context->parser.length != 0u) {
        context->parser_ready_pending = 1;
    }
    *out_processed = processed;
    return CDIN_FRONTEND_TUI_DRAIN_PROGRESS;
}

static cdin_frontend_tui_io_result cdin_tui_drain_backend(
    void *opaque, size_t max_items, size_t *out_processed)
{
    cdin_tui_context *context = (cdin_tui_context *)opaque;
    cdin_backend_status backend_status;
    size_t pumped = 0u;
    size_t processed = 0u;
    if (context == NULL || out_processed == NULL || max_items == 0u) {
        return CDIN_FRONTEND_TUI_IO_FAILURE;
    }
    *out_processed = 0u;
    backend_status = cdin_backend_pump(context->backend, max_items, &pumped);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(context->log->logger, "Backend pump failed in TUI loop: %s",
                     cdin_backend_status_name(backend_status));
        return CDIN_FRONTEND_TUI_IO_FAILURE;
    }
    while (processed < max_items &&
           cdin_backend_frontend_pending(context->transport.frontend) != 0u) {
        cdin_frontend_protocol_message_view message;
        cdin_frontend_protocol_status protocol_status;
        cdin_frontend_tui_model_status model_status;
        int committed = 0;
        protocol_status = cdin_frontend_session_receive(&context->session, &message);
        if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
            MMLLOG_ERROR(context->log->logger, "Frontend receive failed in TUI loop: %s",
                         cdin_frontend_protocol_status_name(protocol_status));
            return CDIN_FRONTEND_TUI_IO_FAILURE;
        }
        model_status = cdin_frontend_tui_receive(
            &context->session, context->model, &message, &committed);
        if (model_status != CDIN_FRONTEND_TUI_MODEL_OK) {
            MMLLOG_ERROR(context->log->logger, "TUI model rejected Backend message: %d",
                         (int)model_status);
            return CDIN_FRONTEND_TUI_IO_FAILURE;
        }
        (void)committed;
        processed++;
    }
    if (cdin_backend_frontend_pending(context->transport.frontend) != 0u) {
        context->backend_ready = 1;
    }
    if (processed != 0u) {
        *out_processed = processed;
        return CDIN_FRONTEND_TUI_DRAIN_PROGRESS;
    }
    if (pumped != 0u) {
        *out_processed = 1u;
        return CDIN_FRONTEND_TUI_DRAIN_PROGRESS;
    }
    return CDIN_FRONTEND_TUI_DRAIN_AGAIN;
}

static int cdin_tui_on_resize(void *opaque)
{
    cdin_tui_context *context = (cdin_tui_context *)opaque;
    uint32_t columns = 80u;
    uint32_t rows = 24u;
    cdin_frontend_protocol_status status;
    if (context == NULL || context->terminal.size(context->terminal.context,
                                                  &columns, &rows) != 0 ||
        columns == 0u || rows == 0u) return -1;
    context->columns = columns;
    context->rows = rows;
    status = cdin_frontend_session_resize(&context->session, columns, rows);
    if (status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(context->log->logger, "Frontend resize failed: %s",
                     cdin_frontend_protocol_status_name(status));
        return -1;
    }
    context->backend_ready = 1;
    return 0;
}

static int cdin_tui_render_frame(void *opaque)
{
    cdin_tui_context *context = (cdin_tui_context *)opaque;
    cdin_frontend_tui_frame frame;
    cdin_frontend_tui_model_status status;
    if (context == NULL || context->model == NULL || !context->terminal.active) return -1;
    status = cdin_frontend_tui_model_get_frame(context->model, &frame);
    if (status != CDIN_FRONTEND_TUI_MODEL_OK) return -1;
    frame.title = context->title;
    if (frame.status == NULL || frame.status[0] == '\0') frame.status = context->help_status;
    if (frame.mode == NULL || frame.mode[0] == '\0') frame.mode = "NORMAL";
    return cdin_frontend_tui_render(&context->terminal, &frame, NULL) ==
        CDIN_FRONTEND_TUI_OK ? 0 : -1;
}

static void cdin_tui_shutdown_loop(void *opaque, cdin_frontend_tui_loop_status reason)
{
    cdin_tui_context *context = (cdin_tui_context *)opaque;
    if (context == NULL || context->shutdown_called) return;
    context->shutdown_called = 1;
    if (context->session_initialized &&
        context->session.state == CDIN_FRONTEND_SESSION_ATTACHED) {
        cdin_frontend_protocol_status status =
            cdin_frontend_session_detach(&context->session);
        if (status != CDIN_FRONTEND_PROTOCOL_OK) {
            MMLLOG_WARN(context->log->logger, "Frontend detach during TUI shutdown failed: %s",
                        cdin_frontend_protocol_status_name(status));
        }
    }
    if (context->model != NULL) {
        cdin_frontend_tui_model_destroy(context->model);
        context->model = NULL;
    }
    if (context->terminal_opened) {
        cdin_frontend_terminal_close(&context->terminal);
        context->terminal_opened = 0;
    }
    if (reason != CDIN_FRONTEND_TUI_LOOP_OK) {
        MMLLOG_WARN(context->log->logger, "TUI event loop exited with status %d", (int)reason);
    }
}

static int cdin_tui_make_scratch_path(cdin_tui_context *context)
{
    unsigned long process_id = CDIN_SMOKE_PROCESS_ID();
    long long timestamp = (long long)time(NULL);
    unsigned int suffix;
    for (suffix = 0u; suffix < 100u; suffix++) {
        FILE *existing;
        int length = snprintf(context->scratch_path, sizeof(context->scratch_path),
                              "cdin-untitled-%lu-%lld-%u.cdin",
                              process_id, timestamp, suffix);
        if (length < 0 || (size_t)length >= sizeof(context->scratch_path)) return -1;
        existing = fopen(context->scratch_path, "rb");
        if (existing == NULL) return 0;
        (void)fclose(existing);
    }
    return -1;
}

static int cdin_tui_drain_initial_snapshot(cdin_tui_context *context)
{
    unsigned int attempts;
    for (attempts = 0u; attempts < 8u; attempts++) {
        size_t processed = 0u;
        cdin_frontend_tui_io_result result =
            cdin_tui_drain_backend(context, 256u, &processed);
        if (result == CDIN_FRONTEND_TUI_IO_FAILURE ||
            result == CDIN_FRONTEND_TUI_DRAIN_EOF) return -1;
        if (result == CDIN_FRONTEND_TUI_DRAIN_AGAIN) {
            return cdin_backend_frontend_pending(context->transport.frontend) == 0u ? 0 : -1;
        }
    }
    return cdin_backend_frontend_pending(context->transport.frontend) == 0u ? 0 : -1;
}

int cdin_frontend_tui_launch(const cdin_options *options, cdin_log *log)
{
    cdin_tui_context context;
    cdin_backend_config config;
    cdin_backend_status backend_status;
    cdin_frontend_terminal_status terminal_status;
    cdin_frontend_protocol_status protocol_status;
    cdin_frontend_protocol_message_view hello_ack;
    cdin_frontend_tui_event_loop loop;
    size_t processed = 0u;
    int result = EXIT_FAILURE;
    int backend_created = 0;
    const char *runtime_root;
    const char *runtime_entry;

    if (options == NULL || log == NULL || log->logger == NULL) return EXIT_FAILURE;
    memset(&context, 0, sizeof(context));
    context.log = log;
    context.wake_read = -1;
    context.wake_write = -1;
    context.transport.backend = NULL;
    cdin_frontend_input_parser_init(&context.parser);

    terminal_status = cdin_frontend_terminal_open(&context.terminal);
    if (terminal_status != CDIN_FRONTEND_TERMINAL_OK) {
        (void)fprintf(stderr,
            "cdin: frontend 'tui' is not launchable: interactive terminal setup failed (%d)\n",
            (int)terminal_status);
        return 3;
    }
    context.terminal_opened = 1;
    if (cdin_tui_create_wakeup_pipe(&context) != 0 ||
        cdin_tui_install_signal_handlers(&context) != 0) {
        MMLLOG_ERROR(log->logger, "Could not initialize TUI wakeup and signal sources");
        goto cleanup;
    }

    runtime_root = options->runtime_root;
    if (runtime_root == NULL || runtime_root[0] == '\0') runtime_root = getenv("CDIN_RUNTIME_ROOT");
    if (runtime_root == NULL || runtime_root[0] == '\0') runtime_root = CDIN_DEFAULT_RUNTIME_ROOT;
    runtime_entry = options->runtime_entry != NULL ? options->runtime_entry : "cdin.runtime";

    cdin_backend_config_init(&config);
    config.runtime_root = runtime_root;
    config.runtime_entry = runtime_entry;
    config.enable_lua = 1;
    config.enable_headless_protocol = 1;
    config.log_output = CDIN_BACKEND_LOG_OUTPUT_CALLBACK;
    config.log_level = CDIN_BACKEND_LOG_INFO;
    config.log_callback = cdin_log_backend_sink;
    config.log_context = log;
    config.wakeup_callback = cdin_tui_backend_wakeup;
    config.wakeup_context = &context;

    backend_status = cdin_backend_create(&config, &context.backend);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend create failed for TUI: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }
    backend_created = 1;
    backend_status = cdin_backend_start(context.backend);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend start failed for TUI: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }
    backend_status = cdin_backend_pump(context.backend, 64u, &processed);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend initial pump failed for TUI: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }

    context.transport.backend = context.backend;
    context.transport.incoming = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    context.transport.outgoing = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    context.client_buffer = (uint8_t *)malloc(CDIN_SMOKE_FRAME_CAPACITY);
    if (context.transport.incoming == NULL || context.transport.outgoing == NULL ||
        context.client_buffer == NULL) {
        MMLLOG_ERROR(log->logger, "Could not allocate Frontend TUI protocol buffers");
        goto cleanup;
    }
    backend_status = cdin_backend_frontend_open(context.backend, &context.transport.frontend);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend frontend open failed for TUI: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }
    context.io.context = &context.transport;
    context.io.read = cdin_inproc_read;
    context.io.write = cdin_inproc_write;
    protocol_status = cdin_frontend_client_init(&context.client, &context.io,
        context.client_buffer, CDIN_SMOKE_FRAME_CAPACITY, CDIN_SMOKE_FRAME_BYTES);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "Frontend TUI client init failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        goto cleanup;
    }
    cdin_frontend_session_init(&context.session, &context.client, NULL, "cdin-tui");
    context.session_initialized = 1;
    protocol_status = cdin_frontend_session_set_capabilities(&context.session, 0u);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) goto protocol_failure;
    protocol_status = cdin_frontend_session_hello(&context.session);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) goto protocol_failure;
    protocol_status = cdin_frontend_session_receive(&context.session, &hello_ack);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK ||
        hello_ack.type != CDIN_FRONTEND_PROTOCOL_HELLO_ACK ||
        !context.session.driver) goto protocol_failure;

    if (context.terminal.size(context.terminal.context,
                              &context.columns, &context.rows) != 0 ||
        context.columns == 0u || context.rows == 0u) {
        context.columns = 80u;
        context.rows = 24u;
    }
    protocol_status = cdin_frontend_session_attach(&context.session, "view-1", "cells",
        context.columns, context.rows);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) goto protocol_failure;
    context.model = cdin_frontend_tui_model_create("view-1", 32u, NULL);
    if (context.model == NULL) {
        MMLLOG_ERROR(log->logger, "Could not create Frontend TUI semantic model");
        goto cleanup;
    }
    if (cdin_tui_drain_initial_snapshot(&context) != 0) {
        MMLLOG_ERROR(log->logger, "Frontend TUI could not apply the initial attached snapshot");
        goto cleanup;
    }
    if (cdin_tui_make_scratch_path(&context) != 0) {
        MMLLOG_ERROR(log->logger, "Could not allocate a unique scratch document path");
        goto cleanup;
    }
    {
        int title_length = snprintf(context.title, sizeof(context.title),
                                    "CDIN | %s", context.scratch_path);
        int help_length = snprintf(context.help_status, sizeof(context.help_status),
            "Ctrl+S Save   Ctrl+Z Undo   Ctrl+Shift+Z Redo   Ctrl+Q Quit");
        if (title_length < 0 || (size_t)title_length >= sizeof(context.title) ||
            help_length < 0 || (size_t)help_length >= sizeof(context.help_status)) {
            goto cleanup;
        }
    }
    protocol_status = cdin_frontend_session_request_command(
        &context.session, "document.new", context.scratch_path);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) goto protocol_failure;
    context.backend_ready = 1;

    memset(&loop, 0, sizeof(loop));
    loop.context = &context;
    loop.wait = cdin_tui_wait;
    loop.drain_terminal = cdin_tui_drain_terminal;
    loop.drain_backend = cdin_tui_drain_backend;
    loop.on_resize = cdin_tui_on_resize;
    loop.render = cdin_tui_render_frame;
    loop.shutdown = cdin_tui_shutdown_loop;
    loop.max_items_per_source = 64u;
    loop.render_initial_frame = 1;
    {
        cdin_frontend_tui_loop_status loop_status =
            cdin_frontend_tui_event_loop_run(&loop);
        result = loop_status == CDIN_FRONTEND_TUI_LOOP_OK ? EXIT_SUCCESS : EXIT_FAILURE;
    }
    goto cleanup;

protocol_failure:
    MMLLOG_ERROR(log->logger, "Frontend TUI session setup failed: %s",
                 cdin_frontend_protocol_status_name(protocol_status));
cleanup:
    if (!context.shutdown_called) {
        cdin_tui_shutdown_loop(&context,
            result == EXIT_SUCCESS ? CDIN_FRONTEND_TUI_LOOP_OK : CDIN_FRONTEND_TUI_LOOP_IO_ERROR);
    }
    if (context.transport.frontend != NULL) {
        backend_status = cdin_backend_frontend_close(context.transport.frontend);
        if (backend_status != CDIN_BACKEND_OK) {
            MMLLOG_ERROR(log->logger, "Backend frontend close failed during TUI shutdown: %s",
                         cdin_backend_status_name(backend_status));
            result = EXIT_FAILURE;
        }
        context.transport.frontend = NULL;
    }
    if (backend_created) {
        backend_status = cdin_backend_shutdown(context.backend, 0);
        if (backend_status != CDIN_BACKEND_OK) {
            MMLLOG_ERROR(log->logger, "Backend shutdown failed after TUI: %s",
                         cdin_backend_status_name(backend_status));
            result = EXIT_FAILURE;
        }
        cdin_backend_destroy(context.backend);
        context.backend = NULL;
    }
    cdin_tui_restore_signal_handlers(&context);
    if (context.wake_read >= 0) (void)close(context.wake_read);
    if (context.wake_write >= 0) (void)close(context.wake_write);
    free(context.client_buffer);
    free(context.transport.outgoing);
    free(context.transport.incoming);
    return result;
}

#else

int cdin_frontend_tui_launch(const cdin_options *options, cdin_log *log)
{
    (void)options;
    if (log != NULL && log->logger != NULL) {
        MMLLOG_WARN(log->logger, "Windows TUI launch remains gated until the Console readiness bridge is implemented");
    }
    (void)fputs("cdin: frontend 'tui' is not launchable: Windows Console readiness integration is not available yet\n",
                stderr);
    return 3;
}

#endif

