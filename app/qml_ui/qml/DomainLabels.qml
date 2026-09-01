import QtQuick

QtObject {
    id: root
    property string language: "en"

    function local(en, vi) {
        return root.language === "vi" ? vi : en
    }

    function runtimeState(state, fallback) {
        switch (String(state || "").toLowerCase()) {
        case "healthy": return local("HEALTHY", "SẴN SÀNG")
        case "local_only": return local("LOCAL ONLY", "CHỈ LOCAL")
        case "starting": return local("STARTING", "ĐANG KHỞI ĐỘNG")
        case "degraded": return local("DEGRADED", "SUY GIẢM")
        case "offline": return local("OFFLINE", "NGOẠI TUYẾN")
        case "misconfigured": return local("MISCONFIGURED", "LỖI CẤU HÌNH")
        case "security_warning": return local("SECURITY WARNING", "CẢNH BÁO BẢO MẬT")
        case "stale_data": return local("STALE DATA", "DỮ LIỆU CŨ")
        case "running": return local("RUNNING", "ĐANG CHẠY")
        case "stopped": return local("STOPPED", "ĐÃ DỪNG")
        case "ready": return local("READY", "SẴN SÀNG")
        case "active": return local("ACTIVE", "HOẠT ĐỘNG")
        case "stale": return local("STALE", "ĐÃ CŨ")
        case "unavailable": return local("UNAVAILABLE", "KHÔNG KHẢ DỤNG")
        case "live": return "LIVE"
        case "failed": return local("FAILED", "THẤT BẠI")
        case "idle": return local("IDLE", "CHƯA CHẠY")
        case "checking": return local("CHECKING", "ĐANG KIỂM TRA")
        default: return fallback || String(state || "").toUpperCase()
        }
    }

    function overallTitle(state, fallback) {
        switch (String(state || "")) {
        case "healthy": return local("All core services are ready", "Các dịch vụ cốt lõi đã sẵn sàng")
        case "local_only": return local("Local MCP is ready", "MCP local đã sẵn sàng")
        case "starting": return local("MCP bridge is starting", "MCP bridge đang khởi động")
        case "degraded": return local("Runtime is degraded", "Runtime đang suy giảm")
        case "offline": return local("MCP server is stopped", "MCP server đã dừng")
        case "misconfigured": return local("Configuration needs attention", "Cấu hình cần được xử lý")
        case "security_warning": return local("Public connector is unauthenticated", "Kết nối công khai chưa bật xác thực")
        case "stale_data": return local("Connector state is stale", "Trạng thái connector đã cũ")
        default: return fallback
        }
    }

    function overallDetail(state, fallback) {
        switch (String(state || "")) {
        case "healthy": return local(
            "Server, bridge, public connector, and live activity stream are available.",
            "Server, bridge, kết nối công khai và luồng hoạt động trực tiếp đều khả dụng."
        )
        case "local_only": return local(
            "The public Cloudflare connector is offline.",
            "Kết nối Cloudflare công khai đang offline."
        )
        case "starting": return local(
            "The bridge is not ready yet.",
            "Bridge chưa sẵn sàng."
        )
        case "degraded": return local(
            "One runtime subsystem needs operator attention.",
            "Một thành phần runtime cần được kiểm tra."
        )
        case "offline": return local(
            "Host MCP requests cannot be served until the local server is running.",
            "Host MCP chưa thể phục vụ request cho tới khi server local chạy lại."
        )
        case "misconfigured": return local(
            "One or more runtime configuration checks are failing.",
            "Một hoặc nhiều kiểm tra cấu hình runtime đang thất bại."
        )
        case "security_warning": return local(
            "The connector is live, but REQUIRE_AUTH is disabled.",
            "Connector đang hoạt động nhưng REQUIRE_AUTH đang tắt."
        )
        case "stale_data": return local(
            "The tunnel process is running, but only a last-known connector URL is available.",
            "Tiến trình tunnel đang chạy nhưng chỉ còn URL connector được ghi nhận trước đó."
        )
        default: return fallback
        }
    }

    function attentionTitle(itemId, fallback) {
        switch (String(itemId || "")) {
        case "server-offline": return local("MCP server is stopped", "MCP server đã dừng")
        case "bridge-not-ready": return local("MCP bridge is not ready", "MCP bridge chưa sẵn sàng")
        case "tunnel-offline": return local("Public connector is offline", "Kết nối công khai đang offline")
        case "connector-stale": return local("Connector URL is stale", "URL connector đã cũ")
        case "connector-unconfirmed": return local("Public connector is not confirmed", "Kết nối công khai chưa được xác nhận")
        case "public-auth-disabled": return local("Authentication is disabled", "Xác thực đang tắt")
        case "stream-state": return local("Activity stream is not live", "Luồng hoạt động không ở trạng thái live")
        case "server-errors": return local("Server errors have been recorded", "Đã ghi nhận lỗi server")
        case "auth-failures": return local("Authentication failures observed", "Đã ghi nhận lỗi xác thực")
        case "rate-limits": return local("Rate limiting has activated", "Rate limit đã được kích hoạt")
        default:
            if (String(itemId || "").indexOf("config-") === 0)
                return local("Configuration validation failed", "Kiểm tra cấu hình thất bại")
            return fallback
        }
    }

    function attentionDetail(itemId, fallback) {
        switch (String(itemId || "")) {
        case "server-offline": return local(
            "Host MCP requests cannot be served until the local server is running.",
            "Host MCP chưa thể phục vụ request cho tới khi server local chạy lại."
        )
        case "bridge-not-ready": return local(
            "The local MCP bridge is not ready.",
            "MCP bridge local chưa sẵn sàng."
        )
        case "tunnel-offline": return local(
            "Local MCP may still work; public ChatGPT connections cannot reach this host.",
            "MCP local vẫn có thể hoạt động; kết nối ChatGPT công khai chưa thể truy cập host này."
        )
        case "connector-stale": return local(
            "A last-known URL exists but it is not currently confirmed active.",
            "Có URL được ghi nhận trước đó nhưng hiện chưa được xác nhận đang hoạt động."
        )
        case "connector-unconfirmed": return local(
            "The tunnel process is running, but there is no confirmed active connector URL.",
            "Tiến trình tunnel đang chạy nhưng chưa có URL connector hoạt động được xác nhận."
        )
        case "public-auth-disabled": return local(
            "The public connector is active without gateway authentication.",
            "Kết nối công khai đang hoạt động nhưng chưa bật xác thực gateway."
        )
        case "stream-state": return local(
            "The structured activity stream is reconnecting or unavailable.",
            "Luồng hoạt động có cấu trúc đang kết nối lại hoặc không khả dụng."
        )
        case "server-errors": return local(
            "Server-side failures were recorded since process start.",
            "Đã ghi nhận lỗi phía server kể từ khi tiến trình khởi động."
        )
        case "auth-failures": return local(
            "Rejected authentication requests were recorded since process start.",
            "Đã ghi nhận request bị từ chối xác thực kể từ khi tiến trình khởi động."
        )
        case "rate-limits": return local(
            "Rate-limited requests were recorded since process start.",
            "Đã ghi nhận request bị rate-limit kể từ khi tiến trình khởi động."
        )
        default:
            if (String(itemId || "").indexOf("config-") === 0)
                return local(
                    "A runtime configuration check is failing.",
                    "Một kiểm tra cấu hình runtime đang thất bại."
                )
            return fallback
        }
    }

    function attentionAction(itemId, fallback) {
        switch (String(itemId || "")) {
        case "server-offline": return local("Start service", "Khởi động")
        case "bridge-not-ready": return local("Run diagnostics", "Chạy chẩn đoán")
        case "tunnel-offline": return local("View tunnel logs", "Xem log tunnel")
        case "connector-stale":
        case "connector-unconfirmed": return local("Refresh", "Làm mới")
        case "public-auth-disabled": return local("Review security", "Xem bảo mật")
        case "stream-state": return local("Open logs", "Mở nhật ký")
        case "server-errors": return local("Run diagnostics", "Chạy chẩn đoán")
        case "auth-failures":
        case "rate-limits": return local("Open runtime logs", "Mở log runtime")
        default:
            if (String(itemId || "").indexOf("config-") === 0)
                return local("Open diagnostics", "Mở chẩn đoán")
            return fallback
        }
    }

    function operationStatus(value) {
        switch (String(value || "").toLowerCase()) {
        case "succeeded": return local("DONE", "XONG")
        case "failed": return local("FAILED", "THẤT BẠI")
        case "timed_out": return local("TIMED OUT", "HẾT THỜI GIAN")
        case "running": return local("RUNNING", "ĐANG CHẠY")
        case "queued": return local("QUEUED", "ĐANG CHỜ")
        case "discovered": return local("DISCOVERED", "ĐÃ PHÁT HIỆN")
        case "cancelled": return local("CANCELLED", "ĐÃ HỦY")
        default: return String(value || "").toUpperCase()
        }
    }

    function workspaceState(value) {
        return String(value || "") === "archived"
            ? local("ARCHIVED", "ĐÃ LƯU TRỮ")
            : local("ACTIVE", "ĐANG HOẠT ĐỘNG")
    }

    function workspaceSummary(active, archived, bytesText) {
        return local(
            active + " active · " + archived + " archived · " + bytesText,
            active + " đang hoạt động · " + archived + " đã lưu trữ · " + bytesText
        )
    }

    function securityLabel(itemId, fallback) {
        switch (String(itemId || "")) {
        case "auth": return local("Authentication", "Xác thực")
        case "workspace-restriction": return local("Workspace restriction", "Giới hạn workspace")
        case "command-policy": return local("Command policy", "Chính sách lệnh")
        case "attribution": return local("Attribution", "Gán danh tính")
        case "chat-workspaces": return local("Chat workspaces", "Workspace theo chat")
        case "chat-isolation": return local("Chat write isolation", "Cô lập ghi theo chat")
        default: return fallback
        }
    }

    function securityValue(itemId, value) {
        var normalized = String(value || "").toLowerCase()
        if (normalized === "enabled") return local("Enabled", "Đã bật")
        if (normalized === "disabled") return local("Disabled", "Đã tắt")
        if (normalized === "restricted") return local("Restricted", "Đã giới hạn")
        if (normalized === "unrestricted") return local("Unrestricted", "Không giới hạn")
        return String(value || "")
    }

    function securityDetail(itemId, fallback) {
        switch (String(itemId || "")) {
        case "auth": return local(
            "Gateway authentication posture for public access.",
            "Trạng thái xác thực gateway cho truy cập công khai."
        )
        case "workspace-restriction": return local(
            "Whether host file operations are constrained to the configured workspace.",
            "Cho biết thao tác file trên host có bị giới hạn trong workspace cấu hình hay không."
        )
        case "command-policy": return local(
            "Commands pass through host policy inspection before execution.",
            "Lệnh được kiểm tra qua policy của host trước khi thực thi."
        )
        case "attribution": return local(
            "Binds host operations to chat/workspace identity.",
            "Gắn thao tác trên host với danh tính chat/workspace."
        )
        case "chat-workspaces": return local(
            "Controls persisted per-chat workspaces.",
            "Điều khiển workspace lưu riêng theo từng chat."
        )
        case "chat-isolation": return local(
            "Controls whether chat writes are confined to the bound workspace.",
            "Điều khiển việc ghi của chat có bị giới hạn trong workspace đã bind hay không."
        )
        default: return fallback
        }
    }

    function metricLabel(itemId, fallback) {
        switch (String(itemId || "")) {
        case "uptime": return local("Uptime", "Thời gian chạy")
        case "requests": return local("Requests", "Request")
        case "errors": return local("5xx errors", "Lỗi 5xx")
        case "p95": return local("p95 latency", "Độ trễ p95")
        case "inflight": return local("In flight", "Đang xử lý")
        case "capacity": return local("Command capacity", "Sức chứa command")
        default: return fallback
        }
    }

    function metricDetail(itemId, fallback) {
        switch (String(itemId || "")) {
        case "uptime": return local("Current server process uptime", "Thời gian chạy của tiến trình server hiện tại")
        case "requests": return local("HTTP requests handled since start", "Số HTTP request đã xử lý từ lúc khởi động")
        case "errors": return local("Server-side HTTP failures", "Lỗi HTTP phía server")
        case "p95": return local("Snapshot percentile; not a time-series graph", "Percentile snapshot; không phải biểu đồ time-series")
        case "inflight": return local("Current requests in flight", "Số request hiện đang xử lý")
        case "capacity": return local("Concurrent command executor slots", "Slot thực thi command đồng thời")
        default: return fallback
        }
    }
}
