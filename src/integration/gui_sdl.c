#if defined(__APPLE__) && !defined(_DARWIN_C_SOURCE)
#define _DARWIN_C_SOURCE 1
#endif
#define _POSIX_C_SOURCE 200809L

#include "cdin/backend.h"
#include "cdin/backend_protocol.h"
#include "cdin/log.h"
#include "cdin/frontend/core/protocol/client.h"
#include "cdin/frontend/core/session/session.h"
#include "cdin/frontend/ui/gui_sdl/gui_sdl.h"
#include "cdin/options.h"
#include "integration/frontend_smoke.h"

#include <SDL3/SDL.h>

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include <process.h>
#define CDIN_GUI_PROCESS_ID() ((unsigned long)_getpid())
#else
#include <unistd.h>
#define CDIN_GUI_PROCESS_ID() ((unsigned long)getpid())
#endif

#ifndef CDIN_DEFAULT_RUNTIME_ROOT
#define CDIN_DEFAULT_RUNTIME_ROOT "./lua"
#endif

#define CDIN_GUI_FRAME_BYTES CDIN_FRONTEND_PROTOCOL_DEFAULT_MAX_FRAME_BYTES
#define CDIN_GUI_FRAME_CAPACITY \
    (CDIN_GUI_FRAME_BYTES + CDIN_FRONTEND_PROTOCOL_FRAME_PREFIX_BYTES)
#define CDIN_GUI_WAIT_ATTEMPTS 1200u
#define CDIN_GUI_SMOKE_PAYLOAD "GUI_SDL_E2E"

typedef struct cdin_gui_transport {
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
    cdin_log *log;
} cdin_gui_transport;

static int cdin_gui_process_inbound_frame(cdin_gui_transport *transport)
{
    cdin_backend_status backend_status;
    cdin_frontend_protocol_message_view inbound;
    size_t processed = 0u;
    cdin_frontend_protocol_status protocol_status =
        cdin_frontend_protocol_decode_frame(
            transport->incoming, transport->incoming_expected,
            &inbound, CDIN_GUI_FRAME_BYTES);
    if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(transport->log->logger, "GUI-SDL inbound frame decode failed: %s",
                     cdin_frontend_protocol_status_name(protocol_status));
        return -1;
    }
    if (transport->outgoing_waiting_ack &&
        inbound.type != CDIN_FRONTEND_PROTOCOL_ACK) {
        MMLLOG_ERROR(transport->log->logger,
                     "GUI-SDL expected ACK while output was backpressured, received %s",
                     cdin_frontend_protocol_message_name(inbound.type));
        return -1;
    }
    backend_status = cdin_backend_frontend_receive(
        transport->frontend, transport->incoming,
        transport->incoming_expected);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(transport->log->logger, "GUI-SDL inbound %s rejected: %s",
                     cdin_frontend_protocol_message_name(inbound.type),
                     cdin_backend_status_name(backend_status));
        return -1;
    }
    backend_status = cdin_backend_pump(transport->backend, 64u, &processed);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(transport->log->logger, "GUI-SDL Backend pump after %s failed: %s",
                     cdin_frontend_protocol_message_name(inbound.type),
                     cdin_backend_status_name(backend_status));
        return -1;
    }
    MMLLOG_INFO(transport->log->logger,
                "GUI-SDL Protocol received %s sequence=%llu processed=%llu pending=%llu",
                cdin_frontend_protocol_message_name(inbound.type),
                (unsigned long long)inbound.sequence,
                (unsigned long long)processed,
                (unsigned long long)cdin_backend_frontend_pending(transport->frontend));
    if (transport->outgoing_waiting_ack) {
        transport->outgoing_waiting_ack = 0;
        transport->outgoing_message_index = 0u;
    }
    return 0;
}

static ptrdiff_t cdin_gui_transport_write(
    void *opaque, const uint8_t *bytes, size_t length)
{
    cdin_gui_transport *transport = (cdin_gui_transport *)opaque;
    size_t consumed = 0u;
    if (transport == NULL || (bytes == NULL && length != 0u)) return -1;
    while (consumed < length) {
        size_t target = transport->incoming_expected == 0u
            ? CDIN_FRONTEND_PROTOCOL_FRAME_PREFIX_BYTES
            : transport->incoming_expected;
        size_t available;
        size_t amount;
        if (transport->incoming_length >= target) return -1;
        available = target - transport->incoming_length;
        amount = length - consumed;
        if (amount > available) amount = available;
        memcpy(transport->incoming + transport->incoming_length,
               bytes + consumed, amount);
        transport->incoming_length += amount;
        consumed += amount;
        if (transport->incoming_expected == 0u &&
            transport->incoming_length == CDIN_FRONTEND_PROTOCOL_FRAME_PREFIX_BYTES) {
            size_t body_length =
                ((size_t)transport->incoming[0] << 24) |
                ((size_t)transport->incoming[1] << 16) |
                ((size_t)transport->incoming[2] << 8) |
                (size_t)transport->incoming[3];
            if (body_length == 0u || body_length > CDIN_GUI_FRAME_BYTES) return -1;
            transport->incoming_expected =
                body_length + CDIN_FRONTEND_PROTOCOL_FRAME_PREFIX_BYTES;
        }
        if (transport->incoming_expected != 0u &&
            transport->incoming_length == transport->incoming_expected) {
            if (cdin_gui_process_inbound_frame(transport) != 0) return -1;
            transport->incoming_length = 0u;
            transport->incoming_expected = 0u;
        }
    }
    return (ptrdiff_t)length;
}

static ptrdiff_t cdin_gui_transport_read(
    void *opaque, uint8_t *buffer, size_t length)
{
    cdin_gui_transport *transport = (cdin_gui_transport *)opaque;
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
        transport->outgoing_message_type =
            (cdin_frontend_protocol_message_type)message.type;
        status = cdin_backend_frontend_encode_message(
            transport->frontend, transport->outgoing_message_index,
            transport->outgoing, CDIN_GUI_FRAME_CAPACITY,
            &transport->outgoing_length);
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
            status = cdin_backend_frontend_consume_control_message(
                transport->frontend);
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

static int cdin_gui_wait_for_attach(
    cdin_backend *backend, cdin_backend_frontend *frontend,
    cdin_frontend_session *session, cdin_log *log)
{
    unsigned int attempt;
    for (attempt = 0u; attempt < CDIN_GUI_WAIT_ATTEMPTS; ++attempt) {
        size_t processed = 0u;
        if (cdin_backend_pump(backend, 64u, &processed) != CDIN_BACKEND_OK) return -1;
        while (cdin_backend_frontend_pending(frontend) != 0u) {
            cdin_frontend_protocol_message_view message;
            if (cdin_frontend_session_receive(session, &message) !=
                CDIN_FRONTEND_PROTOCOL_OK ||
                message.type == CDIN_FRONTEND_PROTOCOL_ERROR) return -1;
            if (message.type == CDIN_FRONTEND_PROTOCOL_UI_FLUSH) {
                char scope[16];
                size_t scope_length = 0u;
                uint64_t sequence = 0u;
                if (cdin_frontend_protocol_payload_get_text(
                        message.payload, message.payload_length, "scope",
                        scope, sizeof(scope), &scope_length) !=
                        CDIN_FRONTEND_PROTOCOL_OK ||
                    cdin_frontend_protocol_payload_get_uint(
                        message.payload, message.payload_length, "sequence",
                        &sequence) != CDIN_FRONTEND_PROTOCOL_OK ||
                    sequence == 0u ||
                    cdin_frontend_session_ack(session, sequence) !=
                        CDIN_FRONTEND_PROTOCOL_OK) {
                    MMLLOG_ERROR(log->logger, "GUI-SDL initial snapshot ACK failed");
                    return -1;
                }
                if (scope_length == 8u &&
                    memcmp(scope, "snapshot", 8u) == 0 &&
                    session->state == CDIN_FRONTEND_SESSION_ATTACHED) return 0;
            }
        }
        SDL_Delay(5u);
    }
    MMLLOG_ERROR(log->logger, "GUI-SDL timed out waiting for ATTACH snapshot");
    return -1;
}

static int cdin_gui_drain(
    cdin_backend *backend, cdin_backend_frontend *frontend,
    cdin_frontend_session *session, cdin_frontend_gui_sdl *gui, cdin_log *log,
    int *out_document_snapshot_committed)
{
    size_t processed = 0u;
    cdin_backend_status backend_status;
    if (out_document_snapshot_committed == NULL) return -1;
    backend_status = cdin_backend_pump(backend, 64u, &processed);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log != NULL ? log->logger : NULL,
                     "GUI-SDL Backend pump before drain failed: %s",
                     cdin_backend_status_name(backend_status));
        return -1;
    }
    *out_document_snapshot_committed = 0;
    while (cdin_backend_frontend_pending(frontend) != 0u) {
        cdin_frontend_protocol_message_view message;
        cdin_frontend_protocol_status protocol_status;
        cdin_frontend_gui_sdl_status gui_status;
        int committed = 0;
        protocol_status = cdin_frontend_session_receive(session, &message);
        if (protocol_status != CDIN_FRONTEND_PROTOCOL_OK) {
            MMLLOG_ERROR(gui->logger, "GUI-SDL response read failed: %s",
                         cdin_frontend_protocol_status_name(protocol_status));
            return -1;
        }
        if (message.type == CDIN_FRONTEND_PROTOCOL_ERROR) {
            char code[64] = { 0 };
            char detail[512] = { 0 };
            size_t code_length = 0u;
            size_t detail_length = 0u;
            (void)cdin_frontend_protocol_payload_get_text(
                message.payload, message.payload_length, "code",
                code, sizeof(code), &code_length);
            (void)cdin_frontend_protocol_payload_get_text(
                message.payload, message.payload_length, "message",
                detail, sizeof(detail), &detail_length);
            MMLLOG_ERROR(gui->logger, "GUI-SDL Backend returned Protocol error %s: %s",
                         code_length != 0u ? code : "UNKNOWN",
                         detail_length != 0u ? detail : "no diagnostic");
            return -1;
        }
        gui_status = cdin_frontend_gui_sdl_apply_message(gui, &message, &committed);
        if (gui_status != CDIN_FRONTEND_GUI_SDL_OK) {
            MMLLOG_ERROR(gui->logger, "GUI-SDL could not apply Backend message %s: status=%d",
                         cdin_frontend_protocol_message_name(message.type),
                         (int)gui_status);
            return -1;
        }
        MMLLOG_INFO(gui->logger, "GUI-SDL applied %s sequence=%llu committed=%d",
                    cdin_frontend_protocol_message_name(message.type),
                    (unsigned long long)message.sequence, committed);
        if (message.type == CDIN_FRONTEND_PROTOCOL_UI_FLUSH && committed != 0) {
            char scope[16];
            size_t scope_length = 0u;
            uint64_t revision = 0u;
            if (cdin_frontend_protocol_payload_get_text(
                    message.payload, message.payload_length, "scope",
                    scope, sizeof(scope), &scope_length) ==
                    CDIN_FRONTEND_PROTOCOL_OK &&
                scope_length == 8u && memcmp(scope, "snapshot", 8u) == 0 &&
                cdin_frontend_protocol_payload_get_uint(
                    message.payload, message.payload_length, "revision",
                    &revision) == CDIN_FRONTEND_PROTOCOL_OK &&
                revision != 0u) {
                *out_document_snapshot_committed = 1;
                MMLLOG_INFO(gui->logger,
                            "GUI-SDL document snapshot committed revision=%llu",
                            (unsigned long long)revision);
            }
        }
    }
    return 0;
}

static int cdin_gui_inject_test_input(void)
{
    /* SDL3's SDL_TextInputEvent owns a const pointer, not an inline buffer.
     * Keep the smoke payload alive while the queued event is dispatched. */
    static const char smoke_text[] = CDIN_GUI_SMOKE_PAYLOAD;
    SDL_Event event;
    memset(&event, 0, sizeof(event));
    event.type = SDL_EVENT_TEXT_INPUT;
    event.text.type = SDL_EVENT_TEXT_INPUT;
    event.text.text = smoke_text;
    if (!SDL_PushEvent(&event)) return -1;
    memset(&event, 0, sizeof(event));
    event.type = SDL_EVENT_KEY_DOWN;
    event.key.type = SDL_EVENT_KEY_DOWN;
    event.key.key = SDLK_S;
    event.key.mod = SDL_KMOD_CTRL;
    event.key.down = true;
    return SDL_PushEvent(&event) ? 0 : -1;
}

static int cdin_gui_saved_bytes_match(const char *path)
{
    static const uint8_t expected[] = CDIN_GUI_SMOKE_PAYLOAD;
    const size_t expected_length = sizeof(expected) - 1u;
    uint8_t actual[sizeof(expected) - 1u];
    FILE *file = fopen(path, "rb");
    size_t count;
    int matches;
    if (file == NULL) return 0;
    count = fread(actual, 1u, expected_length, file);
    matches = count == expected_length &&
        memcmp(actual, expected, expected_length) == 0 &&
        fgetc(file) == EOF && !ferror(file);
    if (fclose(file) != 0) matches = 0;
    return matches;
}

int cdin_frontend_gui_sdl_launch(const cdin_options *options, cdin_log *log)
{
    const char *experimental = getenv("CDIN_ENABLE_EXPERIMENTAL_GUI_SDL");
    cdin_backend_config config;
    cdin_backend *backend = NULL;
    cdin_backend_frontend *frontend = NULL;
    cdin_backend_status backend_status;
    cdin_frontend_protocol_io io;
    cdin_frontend_client client;
    cdin_frontend_session session;
    cdin_frontend_protocol_message_view message;
    cdin_frontend_gui_sdl_config gui_config;
    cdin_frontend_gui_sdl *gui = NULL;
    cdin_gui_transport transport;
    uint8_t *client_buffer = NULL;
    size_t loaded_extensions = 0u;
    size_t processed = 0u;
    unsigned int attempt;
    int backend_created = 0;
    int session_initialized = 0;
    int result = EXIT_FAILURE;
    int quit_requested = 0;
    int document_snapshot_committed = 0;
    int smoke_input_sent = 0;
    int smoke_mode;
    const char *runtime_root;
    const char *runtime_entry;
    char scratch_path[256] = { 0 };

    if (options == NULL || log == NULL || log->logger == NULL) return EXIT_FAILURE;
    smoke_mode = options->check_only != 0;
    if (!smoke_mode &&
        (experimental == NULL || strcmp(experimental, "1") != 0)) {
        (void)fprintf(stderr,
            "cdin: GUI-SDL is experimental; set CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1 to launch it\n");
        return 3;
    }

    memset(&transport, 0, sizeof(transport));
    memset(&session, 0, sizeof(session));
    memset(&io, 0, sizeof(io));
    runtime_root = options->runtime_root;
    if (runtime_root == NULL || runtime_root[0] == '\0') runtime_root = getenv("CDIN_RUNTIME_ROOT");
    if (runtime_root == NULL || runtime_root[0] == '\0') runtime_root = CDIN_DEFAULT_RUNTIME_ROOT;
    runtime_entry = options->runtime_entry != NULL ? options->runtime_entry : "cdin.runtime";

    {
        char expected[32];
        (void)snprintf(expected, sizeof(expected), "%u.%u.%u",
                       CDIN_BACKEND_VERSION_MAJOR, CDIN_BACKEND_VERSION_MINOR,
                       CDIN_BACKEND_VERSION_PATCH);
        if (cdin_backend_version() == NULL || strcmp(cdin_backend_version(), expected) != 0) {
            MMLLOG_FATAL(log->logger, "Backend ABI version mismatch: expected %s, found %s",
                         expected, cdin_backend_version() != NULL ? cdin_backend_version() : "(null)");
            return EXIT_FAILURE;
        }
    }

    cdin_backend_config_init(&config);
    config.runtime_root = runtime_root;
    config.runtime_entry = runtime_entry;
    config.extension_source_root = options->extension_root;
    config.enable_lua = 1;
    config.enable_headless_protocol = 1;
    config.log_output = CDIN_BACKEND_LOG_OUTPUT_CALLBACK;
    config.log_level = CDIN_BACKEND_LOG_INFO;
    config.log_callback = cdin_log_backend_sink;
    config.log_context = log;
    backend_status = cdin_backend_create(&config, &backend);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "GUI-SDL Backend create failed: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }
    backend_created = 1;
    backend_status = cdin_backend_start(backend);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "GUI-SDL Backend start failed: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }
    if (cdin_frontend_extensions_load(
            backend, options, log, &loaded_extensions) != 0) {
        MMLLOG_ERROR(log->logger, "GUI-SDL could not load requested extensions");
        goto cleanup;
    }
    backend_status = cdin_backend_pump(backend, 64u, &processed);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "GUI-SDL initial Backend pump failed: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }

    transport.backend = backend;
    transport.log = log;
    transport.incoming = (uint8_t *)malloc(CDIN_GUI_FRAME_CAPACITY);
    transport.outgoing = (uint8_t *)malloc(CDIN_GUI_FRAME_CAPACITY);
    client_buffer = (uint8_t *)malloc(CDIN_GUI_FRAME_CAPACITY);
    if (transport.incoming == NULL || transport.outgoing == NULL ||
        client_buffer == NULL) {
        MMLLOG_ERROR(log->logger, "GUI-SDL could not allocate Protocol buffers");
        goto cleanup;
    }
    backend_status = cdin_backend_frontend_open(backend, &frontend);
    if (backend_status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "GUI-SDL Frontend open failed: %s",
                     cdin_backend_status_name(backend_status));
        goto cleanup;
    }
    transport.frontend = frontend;
    io.context = &transport;
    io.read = cdin_gui_transport_read;
    io.write = cdin_gui_transport_write;
    if (cdin_frontend_client_init(
            &client, &io, client_buffer, CDIN_GUI_FRAME_CAPACITY,
            CDIN_GUI_FRAME_BYTES) != CDIN_FRONTEND_PROTOCOL_OK) {
        MMLLOG_ERROR(log->logger, "GUI-SDL Frontend client initialization failed");
        goto cleanup;
    }
    cdin_frontend_session_init(&session, &client, log->logger, "cdin-gui-sdl");
    session_initialized = 1;
    if (cdin_frontend_session_set_capabilities(
            &session, cdin_frontend_gui_sdl_supported_capabilities()) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        cdin_frontend_session_hello(&session) != CDIN_FRONTEND_PROTOCOL_OK ||
        cdin_frontend_session_receive(&session, &message) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        message.type != CDIN_FRONTEND_PROTOCOL_HELLO_ACK || !session.driver) {
        MMLLOG_ERROR(log->logger, "GUI-SDL HELLO/HELLO_ACK negotiation failed");
        goto cleanup;
    }
    if (cdin_frontend_session_attach(
            &session, "view-gui-sdl", "pixels", 1000u, 680u) !=
            CDIN_FRONTEND_PROTOCOL_OK ||
        cdin_gui_wait_for_attach(backend, frontend, &session, log) != 0) {
        MMLLOG_ERROR(log->logger, "GUI-SDL could not attach its Driver Session");
        goto cleanup;
    }

    memset(&gui_config, 0, sizeof(gui_config));
    gui_config.session = &session;
    gui_config.logger = log->logger;
    gui_config.window_title = "CDIN — GUI-SDL";
    gui_config.width = 1000u;
    gui_config.height = 680u;
    gui_config.visible_line_capacity = 32u;
    {
        cdin_frontend_gui_sdl_status gui_status =
            cdin_frontend_gui_sdl_create(&gui_config, &gui);
        if (gui_status != CDIN_FRONTEND_GUI_SDL_OK) {
            MMLLOG_ERROR(log->logger, "GUI-SDL adapter create failed: status=%d",
                         (int)gui_status);
            goto cleanup;
        }
    }

    {
        int written = snprintf(scratch_path, sizeof(scratch_path),
                               "cdin-gui-sdl-%lu-%lld.cdin",
                               CDIN_GUI_PROCESS_ID(), (long long)time(NULL));
        if (written < 0 || (size_t)written >= sizeof(scratch_path)) {
            MMLLOG_ERROR(log->logger, "GUI-SDL scratch path exceeds its limit");
            goto cleanup;
        }
    }
    {
        cdin_frontend_protocol_status command_status =
            cdin_frontend_session_request_command(
                &session, "document.new", scratch_path);
        if (command_status != CDIN_FRONTEND_PROTOCOL_OK) {
            MMLLOG_ERROR(log->logger, "GUI-SDL document.new send failed: %s",
                         cdin_frontend_protocol_status_name(command_status));
            goto cleanup;
        }
        MMLLOG_INFO(log->logger, "GUI-SDL requested document.new path=%s", scratch_path);
    }

    for (attempt = 0u;
         attempt < (smoke_mode ? CDIN_GUI_WAIT_ATTEMPTS : UINT32_MAX);
         ++attempt) {
        int newly_committed = 0;
        if (cdin_gui_drain(
                backend, frontend, &session, gui, log, &newly_committed) != 0) {
            result = EXIT_FAILURE;
            break;
        }
        if (newly_committed) document_snapshot_committed = 1;

        if (smoke_mode && document_snapshot_committed && !smoke_input_sent) {
            if (cdin_gui_inject_test_input() != 0) {
                MMLLOG_ERROR(log->logger, "GUI-SDL could not enqueue deterministic SDL input");
                result = EXIT_FAILURE;
                break;
            }
            smoke_input_sent = 1;
        }

        {
            cdin_frontend_gui_sdl_status gui_status =
                cdin_frontend_gui_sdl_pump_events(gui, &quit_requested);
            if (gui_status != CDIN_FRONTEND_GUI_SDL_OK ||
                cdin_frontend_gui_sdl_render(gui) != CDIN_FRONTEND_GUI_SDL_OK) {
                MMLLOG_ERROR(log->logger, "GUI-SDL event pump or render failed");
                result = EXIT_FAILURE;
                break;
            }
        }

        if (smoke_mode && smoke_input_sent &&
            cdin_gui_saved_bytes_match(scratch_path)) {
            MMLLOG_INFO(log->logger,
                        "GUI-SDL live session smoke passed: SDL text input, Runtime Ctrl+S and exact-byte save");
            result = EXIT_SUCCESS;
            break;
        }
        if (!smoke_mode && quit_requested) {
            result = EXIT_SUCCESS;
            break;
        }
        SDL_Delay(5u);
    }
    if (smoke_mode && result != EXIT_SUCCESS) {
        MMLLOG_ERROR(log->logger, "GUI-SDL live session smoke did not reach an exact-byte save");
    }

cleanup:
    if (gui != NULL) cdin_frontend_gui_sdl_destroy(gui);
    if (session_initialized &&
        session.state == CDIN_FRONTEND_SESSION_ATTACHED) {
        cdin_frontend_protocol_status status =
            cdin_frontend_session_detach(&session);
        if (status != CDIN_FRONTEND_PROTOCOL_OK) {
            MMLLOG_WARN(log->logger, "GUI-SDL Session detach failed: %s",
                        cdin_frontend_protocol_status_name(status));
        }
    }
    if (frontend != NULL) {
        backend_status = cdin_backend_frontend_close(frontend);
        if (backend_status != CDIN_BACKEND_OK) {
            MMLLOG_ERROR(log->logger, "GUI-SDL Frontend close failed: %s",
                         cdin_backend_status_name(backend_status));
            result = EXIT_FAILURE;
        }
    }
    if (backend_created && loaded_extensions != 0u &&
        cdin_frontend_extensions_unload(
            backend, options, log, loaded_extensions) != 0) {
        result = EXIT_FAILURE;
    }
    if (backend_created) {
        backend_status = cdin_backend_shutdown(backend, 0);
        if (backend_status != CDIN_BACKEND_OK) {
            MMLLOG_ERROR(log->logger, "GUI-SDL Backend shutdown failed: %s",
                         cdin_backend_status_name(backend_status));
            result = EXIT_FAILURE;
        }
        cdin_backend_destroy(backend);
    }
    if (smoke_mode && scratch_path[0] != '\0') (void)remove(scratch_path);
    free(client_buffer);
    free(transport.outgoing);
    free(transport.incoming);
    return result;
}
