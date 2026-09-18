"""HTML builders for the redesigned Qt About panel.

Provides rich Cyberpunk / Modern Command Center layouts matching the BotQuangAnh
desktop theme: dark graphite surfaces, lime accents, parameter pills, tool cards,
and step-by-step ChatGPT Web workflow cards.
"""

from __future__ import annotations

from app.cli.desktop_qt.theme import COLORS
from app.cli.desktop_views.about import (
    CHATGPT_PROMPT_TEMPLATE_EN,
    CHATGPT_PROMPT_TEMPLATE_VI,
)


def _css_styles() -> str:
    """Return common CSS styles supported by Qt QTextDocument rich text engine."""
    return f"""
    body {{
        background-color: {COLORS["canvas"]};
        color: {COLORS["text"]};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        font-size: 13px;
        line-height: 1.5;
        margin: 6px 10px;
    }}
    a {{
        color: {COLORS["lime"]};
        text-decoration: none;
    }}
    .hero-card {{
        background-color: {COLORS["surface"]};
        border: 1px solid {COLORS["border"]};
        margin-bottom: 14px;
    }}
    .hero-title {{
        color: {COLORS["lime"]};
        font-size: 15px;
        font-weight: bold;
    }}
    .hero-badge {{
        background-color: {COLORS["panel_raised"]};
        color: {COLORS["lime"]};
        border: 1px solid {COLORS["border_strong"]};
        font-size: 11px;
        font-weight: bold;
        padding: 3px 8px;
    }}
    .hero-desc {{
        color: {COLORS["muted"]};
        font-size: 12px;
        margin-top: 6px;
    }}
    .section-card {{
        background-color: {COLORS["panel"]};
        border: 1px solid {COLORS["border_subtle"]};
        margin-bottom: 14px;
    }}
    .section-header-title {{
        color: {COLORS["lime"]};
        font-size: 13px;
        font-weight: bold;
    }}
    .section-header-badge {{
        background-color: {COLORS["graphite_raised"]};
        color: {COLORS["muted"]};
        border: 1px solid {COLORS["border"]};
        font-size: 10px;
        font-weight: bold;
        padding: 2px 6px;
    }}
    .tool-card {{
        background-color: {COLORS["graphite_mid"]};
        border: 1px solid {COLORS["border_subtle"]};
        margin-bottom: 8px;
    }}
    .tool-name {{
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 13px;
        font-weight: bold;
        color: {COLORS["lime"]};
    }}
    .badge-kind {{
        background-color: {COLORS["graphite_raised"]};
        color: {COLORS["success"]};
        font-size: 10px;
        font-weight: bold;
        padding: 2px 6px;
        border: 1px solid {COLORS["border"]};
    }}
    .badge-highlight {{
        background-color: #2b2512;
        color: {COLORS["warning"]};
        font-size: 10px;
        font-weight: bold;
        padding: 2px 6px;
        border: 1px solid #554018;
    }}
    .badge-danger {{
        background-color: #2b1414;
        color: {COLORS["danger"]};
        font-size: 10px;
        font-weight: bold;
        padding: 2px 6px;
        border: 1px solid #5a2020;
    }}
    .param-pill {{
        background-color: {COLORS["graphite_inset"]};
        color: {COLORS["success"]};
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 11px;
        padding: 2px 5px;
        border: 1px solid {COLORS["border_subtle"]};
    }}
    .req-pill {{
        background-color: #2c2214;
        color: {COLORS["warning"]};
        font-size: 10px;
        font-weight: bold;
        padding: 1px 4px;
        border: 1px solid #4a3818;
    }}
    .opt-pill {{
        background-color: {COLORS["graphite_deep"]};
        color: {COLORS["subtle"]};
        font-size: 10px;
        padding: 1px 4px;
        border: 1px solid {COLORS["border_subtle"]};
    }}
    .callout-box {{
        background-color: #1a1710;
        border: 1px solid #4e3d1b;
        margin-bottom: 14px;
    }}
    .callout-title {{
        color: {COLORS["warning"]};
        font-size: 12px;
        font-weight: bold;
    }}
    .callout-desc {{
        color: #d8c7a2;
        font-size: 12px;
    }}
    .step-card {{
        background-color: {COLORS["panel"]};
        border: 1px solid {COLORS["border"]};
        margin-bottom: 14px;
    }}
    .step-badge {{
        background-color: {COLORS["lime"]};
        color: {COLORS["canvas"]};
        font-size: 11px;
        font-weight: bold;
        padding: 2px 8px;
    }}
    .step-title {{
        color: {COLORS["text"]};
        font-size: 14px;
        font-weight: bold;
    }}
    .prompt-box {{
        background-color: {COLORS["graphite_deep"]};
        border: 1px solid {COLORS["border_strong"]};
        color: #bbf7d0;
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
        font-size: 12px;
        line-height: 1.45;
        padding: 12px;
    }}
    .table-faq {{
        background-color: {COLORS["panel"]};
        border: 1px solid {COLORS["border"]};
    }}
    .table-faq th {{
        background-color: {COLORS["surface_2"]};
        color: {COLORS["lime"]};
        font-size: 11px;
        text-align: left;
        padding: 8px 10px;
        border-bottom: 1px solid {COLORS["border"]};
    }}
    .table-faq td {{
        padding: 8px 10px;
        border-bottom: 1px solid {COLORS["border_subtle"]};
        font-size: 12px;
    }}
    """


def build_readme_html(is_vi: bool = True) -> str:
    """Build aesthetic Cyberpunk HTML for the 17 MCP tools."""
    css = _css_styles()

    if is_vi:
        hero_title = "⚡ BOTQUANGANH HOST MCP — DANH MỤC CÔNG CỤ & ĐẶC TẢ KỸ THUẬT"
        hero_badge = "17 TOOLS HOẠT ĐỘNG"
        hero_desc = (
            "Máy chủ MCP chuyên dụng vận hành trên giao thức <b>Streamable HTTP (Stateless JSON)</b> "
            "kết hợp <b>Cloudflare Tunnel</b> mã hóa đầu cuối. Hệ thống cung cấp 17 công cụ có kiểm soát "
            "an toàn hai pha (Two-phase Journal) và cô lập phiên làm việc tuyệt đối."
        )

        warn_title = "⚠️ LƯU Ý QUAN TRỌNG: CHÍNH SÁCH BẮT BUỘC RÀNG BUỘC PHIÊN (ATTRIBUTION_MODE=enforce)"
        warn_desc = (
            "Hệ thống yêu cầu <b>host_workspace_bind(chat_id=\"...\")</b> là công cụ ĐẦU TIÊN phải gọi "
            "trong mỗi phiên chat. Nếu gọi các công cụ tệp tin hoặc lệnh shell trước khi bind, server sẽ "
            "từ chối ngay lập tức với mã lỗi <b>E6 (BIND_REQUIRED)</b>."
        )

        cat1_title = "1. HỆ THỐNG & SỨC KHỎE (SYSTEM & HEALTH)"
        cat1_badge = "2 TOOLS"
        cat2_title = "2. KIẾN THỨC & TÀI LIỆU HƯỚNG DẪN (KNOWLEDGE & GUIDES)"
        cat2_badge = "1 TOOL"
        cat3_title = "3. THAO TÁC TỆP TIN & THƯ MỤC (FILESYSTEM TOOLS)"
        cat3_badge = "7 TOOLS"
        cat4_title = "4. THỰC THI LỆNH TRÊN HOST (COMMAND EXECUTION)"
        cat4_badge = "2 TOOLS"
        cat5_title = "5. QUẢN LÝ PHIÊN & CHAT WORKSPACE (WORKSPACE TOOLS)"
        cat5_badge = "2 TOOLS"
        cat6_title = "6. BỘ CÔNG CỤ ĐIỀU TRA CTF (CTF INVESTIGATION SUITE)"
        cat6_badge = "3 TOOLS"

        lbl_params = "Tham số:"
        lbl_returns = "Trả về:"
        lbl_guardrail = "Bảo vệ:"
        lbl_req = "bắt buộc"
        lbl_opt = "tùy chọn"
        lbl_recommend = "KHUYÊN DÙNG"
    else:
        hero_title = "⚡ BOTQUANGANH HOST MCP — TOOL CATALOG & SPECIFICATION"
        hero_badge = "17 TOOLS ACTIVE"
        hero_desc = (
            "Dedicated host MCP server operating over <b>Streamable HTTP (Stateless JSON)</b> "
            "paired with <b>Cloudflare Tunnel</b> encryption. Delivers 17 guarded tools featuring "
            "two-phase journal audit trails and strict per-chat session isolation."
        )

        warn_title = "⚠️ CRITICAL NOTICE: STRICT SESSION BINDING POLICY (ATTRIBUTION_MODE=enforce)"
        warn_desc = (
            "The system requires <b>host_workspace_bind(chat_id=\"...\")</b> as the VERY FIRST tool call "
            "in every conversation. Attempting to call filesystem or execution tools before binding triggers "
            "an immediate rejection with error code <b>E6 (BIND_REQUIRED)</b>."
        )

        cat1_title = "1. SYSTEM & HEALTH TOOLS"
        cat1_badge = "2 TOOLS"
        cat2_title = "2. KNOWLEDGE & GUIDES TOOLS"
        cat2_badge = "1 TOOL"
        cat3_title = "3. FILESYSTEM & DIRECTORY TOOLS"
        cat3_badge = "7 TOOLS"
        cat4_title = "4. COMMAND EXECUTION TOOLS"
        cat4_badge = "2 TOOLS"
        cat5_title = "5. WORKSPACE & SESSION TOOLS"
        cat5_badge = "2 TOOLS"
        cat6_title = "6. CTF INVESTIGATION SUITE"
        cat6_badge = "3 TOOLS"

        lbl_params = "Parameters:"
        lbl_returns = "Returns:"
        lbl_guardrail = "Guardrails:"
        lbl_req = "required"
        lbl_opt = "optional"
        lbl_recommend = "RECOMMENDED"

    return f"""<!DOCTYPE html>
<html>
<head><style>{css}</style></head>
<body>

<!-- HERO CARD -->
<table width="100%" cellpadding="12" cellspacing="0" class="hero-card">
  <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="hero-title">{hero_title}</td>
          <td align="right"><span class="hero-badge">{hero_badge}</span></td>
        </tr>
      </table>
      <div class="hero-desc">{hero_desc}</div>
    </td>
  </tr>
</table>

<!-- CALLOUT WARNING -->
<table width="100%" cellpadding="10" cellspacing="0" class="callout-box">
  <tr>
    <td>
      <div class="callout-title">{warn_title}</div>
      <div class="callout-desc" style="margin-top: 4px;">{warn_desc}</div>
    </td>
  </tr>
</table>

<!-- SECTION 1: SYSTEM & HEALTH -->
<table width="100%" cellpadding="10" cellspacing="0" class="section-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="section-header-title">📡 {cat1_title}</td>
          <td align="right"><span class="section-header-badge">{cat1_badge}</span></td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 10px;">
      <!-- health_check -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">health_check</span>
            <span class="badge-kind">HEALTH / PING</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Kiểm tra khả năng kết nối tới máy chủ MCP và thu thập các chỉ số vận hành cơ bản.' if is_vi else 'Verify server reachability and collect fundamental runtime telemetry.'}
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b> <i>{'Không có tham số' if is_vi else 'None'}</i> &nbsp;·&nbsp;
              <b>{lbl_returns}</b> <span class="param-pill">ok</span>, <span class="param-pill">service</span>, <span class="param-pill">version</span>, <span class="param-pill">server_time</span>, <span class="param-pill">workspace</span>, <span class="param-pill">command_policy</span>, <span class="param-pill">metrics</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- get_capabilities -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">get_capabilities</span>
            <span class="badge-kind">DISCOVERY</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Đọc danh sách năng lực chi tiết của máy chủ, hạn mức an toàn đang kích hoạt và 17 công cụ có sẵn.' if is_vi else 'Retrieve full service capabilities, active safety bounds, and all 17 registered MCP tools.'}
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b> <i>{'Không có tham số' if is_vi else 'None'}</i> &nbsp;·&nbsp;
              <b>{lbl_returns}</b> <span class="param-pill">tools [17]</span>, <span class="param-pill">limits</span> (timeout 60s, file 3MB, stdout 500KB, concurrent 100)
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

<!-- SECTION 2: KNOWLEDGE & GUIDES -->
<table width="100%" cellpadding="10" cellspacing="0" class="section-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="section-header-title">📖 {cat2_title}</td>
          <td align="right"><span class="section-header-badge">{cat2_badge}</span></td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 10px;">
      <!-- host_knowledge -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_knowledge</span>
            <span class="badge-kind">GUIDES / CATALOG</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Tra cứu tài liệu quy tắc làm việc hoặc kiểm tra danh mục phần mềm/công cụ CLI đã cài đặt trên host.' if is_vi else 'Inspect workspace operating procedures or verify installed CLI packages and developer tools.'}
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">section</span> <span class="req-pill">{lbl_req}</span> ("overview" | "guide" | "tools" | "search" | "all"),
              <span class="param-pill">query</span> <span class="opt-pill">{lbl_opt}</span>,
              <span class="param-pill">category</span> <span class="opt-pill">{lbl_opt}</span>,
              <span class="param-pill">available_only</span> <span class="opt-pill">true</span>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

<!-- SECTION 3: FILESYSTEM TOOLS -->
<table width="100%" cellpadding="10" cellspacing="0" class="section-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="section-header-title">📁 {cat3_title}</td>
          <td align="right"><span class="section-header-badge">{cat3_badge}</span></td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 10px;">
      <!-- host_list_directory -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_list_directory</span>
            <span class="badge-kind">FS / DIR</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Liệt kê tệp tin và thư mục con tại đường dẫn chỉ định với giới hạn mục tối đa an toàn.' if is_vi else 'List directory contents with optional recursive traversal and bounded output size.'}
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">path</span> <span class="opt-pill">cwd</span>,
              <span class="param-pill">recursive</span> <span class="opt-pill">false</span>,
              <span class="param-pill">max_entries</span> <span class="opt-pill">200</span> (max 1000)
            </div>
          </td>
        </tr>
      </table>

      <!-- host_read_file -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_read_file</span>
            <span class="badge-kind">FS / READ-ONLY</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Đọc nội dung tệp tin văn bản UTF-8 có bảo vệ chống cạn kiệt bộ nhớ (ngưỡng 3MB).' if is_vi else 'Read UTF-8 text file contents with offset/limit paging and a hard 3MB safety limit.'}
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">path</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">offset</span> <span class="opt-pill">0</span>,
              <span class="param-pill">limit</span> <span class="opt-pill">{lbl_opt}</span>,
              <span class="param-pill">max_bytes</span> <span class="opt-pill">3,000,000</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- host_replace_in_file -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card" style="border-color: {COLORS['border_strong']};">
        <tr>
          <td>
            <span class="tool-name">host_replace_in_file</span>
            <span class="badge-highlight">{lbl_recommend}</span>
            <span class="badge-kind">FS / SURGICAL EDIT</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Thay thế chính xác một đoạn văn bản/mã nguồn theo số lần xuất hiện kỳ vọng. Chống ghi đè làm mất mã.' if is_vi else 'Surgically substitute an exact snippet with strict occurrence validation. Prevents file clobbering.'}
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">path</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">old_text</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">new_text</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">expected_count</span> <span class="opt-pill">1</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- host_write_file -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_write_file</span>
            <span class="badge-kind">FS / OVERWRITE</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Tạo mới hoặc ghi đè toàn bộ tệp tin văn bản UTF-8 (chỉ dùng khi tạo file mới hoặc có chủ ý ghi đè).' if is_vi else 'Create a new file or completely overwrite an existing one (use with caution).' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">path</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">content</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">overwrite</span> <span class="opt-pill">true</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- host_append_file -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_append_file</span>
            <span class="badge-kind">FS / APPEND</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Nối thêm nội dung văn bản vào cuối tệp tin đã có (tự động tạo tệp nếu chưa tồn tại).' if is_vi else 'Append text content to the end of a file (auto-creates file if absent).' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">path</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">content</span> <span class="req-pill">{lbl_req}</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- host_make_directory -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_make_directory</span>
            <span class="badge-kind">FS / MKDIR</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Tạo thư mục mới trên hệ thống tệp tin (tự động tạo thư mục cha mkdir -p).' if is_vi else 'Create a directory on the host filesystem (recursively creates parents by default).' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">path</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">parents</span> <span class="opt-pill">true</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- host_search_text -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_search_text</span>
            <span class="badge-kind">FS / SEARCH</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Tìm kiếm chuỗi ký tự đệ quy bên trong các tệp tin với bộ đếm thời gian an toàn 15s chống treo.' if is_vi else 'Recursively search files for an exact text snippet with a 15-second deadline timer.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">query</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">path</span> <span class="opt-pill">cwd</span>,
              <span class="param-pill">max_results</span> <span class="opt-pill">50</span> (max 200)
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

<!-- SECTION 4: COMMAND EXECUTION -->
<table width="100%" cellpadding="10" cellspacing="0" class="section-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="section-header-title">⚡ {cat4_title}</td>
          <td align="right"><span class="section-header-badge">{cat4_badge}</span></td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 10px;">
      <!-- host_check_command -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_check_command</span>
            <span class="badge-kind">EXEC / POLICY DRY-RUN</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Kiểm tra chính sách an toàn của câu lệnh trước khi chạy mà KHÔNG thực thi lệnh.' if is_vi else 'Dry-run inspection of command authorization and risk score under active policy.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">command</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">cwd</span> <span class="opt-pill">{lbl_opt}</span> &nbsp;·&nbsp;
              <b>{lbl_returns}</b> <span class="param-pill">allowed</span> (bool), <span class="param-pill">reason</span>, <span class="param-pill">risk_score</span>, <span class="param-pill">matched_patterns</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- host_run_command -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_run_command</span>
            <span class="badge-highlight">GUARDED SHELL</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Thực thi câu lệnh shell có kiểm duyệt trên host. Chặn phá hoại, ẩn bí mật và tự động cắt bớt đầu ra >500KB.' if is_vi else 'Execute a guarded shell command with pattern blocking, credential masking, and 500KB stdout truncation.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">command</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">cwd</span> <span class="opt-pill">workspace</span>,
              <span class="param-pill">timeout_seconds</span> <span class="opt-pill">30</span> (max 60),
              <span class="param-pill">check_first</span> <span class="opt-pill">true</span>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

<!-- SECTION 5: WORKSPACE & SESSION -->
<table width="100%" cellpadding="10" cellspacing="0" class="section-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="section-header-title">🗂️ {cat5_title}</td>
          <td align="right"><span class="section-header-badge">{cat5_badge}</span></td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 10px;">
      <!-- host_workspace_bind -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card" style="border-color: {COLORS['border_strong']};">
        <tr>
          <td>
            <span class="tool-name">host_workspace_bind</span>
            <span class="badge-danger">MANDATORY FIRST CALL</span>
            <span class="badge-kind">ISOLATION</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'RÀNG BUỘC PHIÊN CHAT VỚI WORKSPACE RIÊNG BIỆT. Tạo thư mục ~/Downloads/bqa-workspaces/&lt;chat_id&gt;/, journal.jsonl và STATE.md.' if is_vi else 'BIND SESSION TO A DEDICATED PER-CHAT WORKSPACE. Initializes isolated directory, journal.jsonl, and STATE.md.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">chat_id</span> <span class="req-pill">{lbl_req}</span> (6-64 ký tự [a-zA-Z0-9._-]) &nbsp;·&nbsp;
              <b>{lbl_guardrail}</b> {'Bỏ qua sẽ bị mã lỗi E6 (BIND_REQUIRED)' if is_vi else 'Skipping triggers immediate E6 (BIND_REQUIRED)'}
            </div>
          </td>
        </tr>
      </table>

      <!-- host_save_note -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">host_save_note</span>
            <span class="badge-kind">WORKSPACE / NOTE</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Lưu ghi chú bền vững hoặc tóm tắt mốc công việc vào thư mục notes/ của phiên làm việc.' if is_vi else 'Save durable notes or milestone summaries to the active chat workspace notes/ directory.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">title</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">content</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">tags</span> <span class="opt-pill">{lbl_opt}</span>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

<!-- SECTION 6: CTF SUITE -->
<table width="100%" cellpadding="10" cellspacing="0" class="section-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="section-header-title">🚩 {cat6_title}</td>
          <td align="right"><span class="section-header-badge">{cat6_badge}</span></td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 10px;">
      <!-- ctf_triage_artifact -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">ctf_triage_artifact</span>
            <span class="badge-kind">CTF / ARTIFACT</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Phân tích sơ bộ tệp tin challenge: MIME/magic, hashes (MD5, SHA256), entropy và trích xuất chuỗi nghi vấn.' if is_vi else 'Inspect challenge artifacts: MIME types, cryptographic hashes, entropy scoring, and suspicious strings.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">path</span> <span class="req-pill">{lbl_req}</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- ctf_fetch_url -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">ctf_fetch_url</span>
            <span class="badge-kind">CTF / HTTP REQ</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Gửi HTTP request có lưu vết và kiểm soát tới mục tiêu challenge web CTF được cấp phép.' if is_vi else 'Send audited, scoped HTTP requests to authorized CTF web challenge targets.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">url</span> <span class="req-pill">{lbl_req}</span>,
              <span class="param-pill">method</span> <span class="opt-pill">"GET"</span>,
              <span class="param-pill">headers</span> <span class="opt-pill">{lbl_opt}</span>,
              <span class="param-pill">data</span> <span class="opt-pill">{lbl_opt}</span>
            </div>
          </td>
        </tr>
      </table>

      <!-- ctf_render_fetch_result -->
      <table width="100%" cellpadding="8" cellspacing="0" class="tool-card">
        <tr>
          <td>
            <span class="tool-name">ctf_render_fetch_result</span>
            <span class="badge-kind">CTF / INSPECT</span>
            <div style="color: {COLORS['text']}; margin: 4px 0;">
              {'Hiển thị kết quả phản hồi HTTP từ ctf_fetch_url dưới dạng cấu trúc trực quan.' if is_vi else 'Render or inspect raw fetch responses from ctf_fetch_url in structured format.' }
            </div>
            <div style="color: {COLORS['subtle']}; font-size: 11px;">
              <b>{lbl_params}</b>
              <span class="param-pill">fetch_id</span> <span class="req-pill">{lbl_req}</span>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>

</body>
</html>"""


def build_chatgpt_guide_html(is_vi: bool = True) -> str:
    """Build aesthetic Cyberpunk HTML for ChatGPT Web integration guide."""
    css = _css_styles()
    prompt_text = (
        CHATGPT_PROMPT_TEMPLATE_VI if is_vi else CHATGPT_PROMPT_TEMPLATE_EN
    ).replace("<", "&lt;").replace(">", "&gt;")

    if is_vi:
        hero_title = "🌐 HƯỚNG DẪN TÍCH HỢP TOÀN DIỆN VỚI CHATGPT WEB"
        hero_badge = "CLOUDFLARE TUNNEL"
        hero_desc = (
            "Kết nối an toàn giữa <b>ChatGPT Web (chatgpt.com)</b> và máy chủ BotQuangAnh MCP "
            "thông qua đường hầm mã hóa Cloudflare Tunnel mà <b>không cần mở cổng mạng (port-forwarding)</b>."
        )

        step1_title = "Khởi động dịch vụ & Lấy URL Connector"
        step1_body = """
        <ol style="margin: 6px 0; padding-left: 20px;">
          <li><b>Kiểm tra dịch vụ:</b> Tại tab <b>Runtime</b> trên desktop UI, đảm bảo 2 thành phần <b>MCP bridge</b> và <b>Cloudflare tunnel</b> đều đang hiển thị trạng thái màu xanh: <i>running</i>.</li>
          <li><b>Lấy URL Connector:</b> Bấm nút <b>Sao chép URL connector</b> trên thanh công cụ của tab này, hoặc nút Sao chép cạnh trường Endpoint trong tab Runtime.</li>
          <li><b>Định dạng URL hợp lệ:</b>
            <div style="margin: 6px 0; padding: 6px 10px; background-color: #151e1b; border: 1px solid #2a3632; font-family: monospace; color: #a3ff12;">
              https://&lt;subdomain-ngau-nhien&gt;.trycloudflare.com/mcp
            </div>
            <span style="color: #f4b942;">* QUAN TRỌNG:</span> URL hợp lệ <b>bắt buộc phải có đuôi <code>/mcp</code></b>. Không sử dụng URL trang chủ.
          </li>
        </ol>
        """

        step2_title = "Cấu hình trên ChatGPT Web (chatgpt.com)"
        step2_body = """
        <table width="100%" cellpadding="8" cellspacing="0">
          <tr>
            <td width="50%" valign="top" style="background-color: #151e1b; border: 1px solid #202b28;">
              <b style="color: #42d5ad;">LỰA CHỌN A: DÙNG CONNECTED APPS</b><br/>
              <i>(Áp dụng khi tài khoản ChatGPT có mục Connected Apps / Developer)</i>
              <ol style="margin: 6px 0; padding-left: 18px; font-size: 12px; color: #d1dad5;">
                <li>Đăng nhập <a href="https://chatgpt.com">chatgpt.com</a>.</li>
                <li>Vào <b>Settings</b> &rarr; <b>Connected Apps</b> (hoặc Developer &rarr; MCP Servers).</li>
                <li>Bấm <b>Add MCP Server</b>:
                  <ul style="padding-left: 14px; margin-top: 4px;">
                    <li><b>Name:</b> BotQuangAnh MCP</li>
                    <li><b>URL:</b> Dán URL đuôi <code>/mcp</code></li>
                    <li><b>Transport:</b> Streamable HTTP</li>
                    <li><b>Auth:</b> None (hoặc Bearer nếu bật REQUIRE_AUTH)</li>
                  </ul>
                </li>
                <li>Bấm <b>Save / Connect</b>. ChatGPT sẽ tự động nạp 17 công cụ.</li>
              </ol>
            </td>
            <td width="50%" valign="top" style="background-color: #17221f; border: 1px solid #2a3d36;">
              <b style="color: #a3ff12;">LỰA CHỌN B: TẠO CUSTOM GPT (KHUYÊN DÙNG ⭐)</b><br/>
              <i>(Trải nghiệm mượt mà nhất, kèm theo System Instructions đầy đủ)</i>
              <ol style="margin: 6px 0; padding-left: 18px; font-size: 12px; color: #d1dad5;">
                <li>Truy cập <a href="https://chatgpt.com/gpts/editor">chatgpt.com/gpts/editor</a>.</li>
                <li>Mục <b>Configure</b>:
                  <ul style="padding-left: 14px; margin-top: 4px;">
                    <li><b>Name:</b> BotQuangAnh Host Assistant</li>
                    <li><b>Instructions:</b> Dán <b>Prompt mẫu</b> ở Bước 4 dưới đây.</li>
                  </ul>
                </li>
                <li>Mục <b>Actions / MCP Connectors</b>:
                  <ul style="padding-left: 14px; margin-top: 4px;">
                    <li>Thêm Connector trỏ tới URL <code>/mcp</code>.</li>
                  </ul>
                </li>
                <li>Lưu GPT với quyền riêng tư <b>Only me</b>.</li>
              </ol>
            </td>
          </tr>
        </table>
        """

        step3_title = "Quy tắc Bắt tay 3 bước bắt buộc (Handshake Protocol)"
        step3_body = """
        <div style="background-color: #241a10; border: 1px solid #5a3d1b; padding: 8px 10px; margin-bottom: 8px;">
          <b style="color: #f4b942;">BƯỚC BẮT BUỘC 1: KHỞI TẠO VÀ RÀNG BUỘC PHIÊN (WORKSPACE BINDING)</b><br/>
          Trong mỗi cuộc hội thoại mới, lệnh <b>ĐẦU TIÊN</b> mà ChatGPT phải gọi là:<br/>
          <div style="margin: 6px 0; padding: 6px; background-color: #0e1513; border: 1px solid #3a4a44; font-family: monospace; color: #a3ff12;">
            host_workspace_bind(chat_id="bqa-session-xxxxx")
          </div>
          <span style="color: #ff6b61; font-weight: bold;">CẢNH BÁO:</span> Nếu ChatGPT gọi bất kỳ tool nào khác trước khi bind, máy chủ sẽ lập tức từ chối với mã lỗi <b>E6 (BIND_REQUIRED)</b>!
        </div>
        <div style="font-size: 12px; color: #d1dad5; line-height: 1.6;">
          <b>BƯỚC 2: KHÁM PHÁ MÔI TRƯỜNG &amp; CÔNG CỤ:</b><br/>
          &bull; Gọi <code>host_knowledge(section="overview")</code> để kiểm tra phạm vi workspace và policy an toàn.<br/>
          &bull; Gọi <code>host_knowledge(section="tools", query="&lt;tool_name&gt;")</code> để xác minh phần mềm đã cài đặt trên máy host trước khi gọi.<br/><br/>
          <b>BƯỚC 3: THỰC HIỆN TÁC VỤ AN TOÀN:</b><br/>
          &bull; Kiểm tra lệnh trước khi chạy: <code>host_check_command(command="...")</code>.<br/>
          &bull; Thực thi lệnh có bảo vệ: <code>host_run_command(command="...", cwd="...")</code>.<br/>
          &bull; Thay thế mã nguồn chính xác: Ưu tiên <code>host_replace_in_file</code> thay vì ghi đè cả file.<br/>
          &bull; Lưu lại tiến trình: <code>host_save_note(title="...", content="...")</code>.
        </div>
        """

        step4_title = "Mẫu System Instructions chuẩn cho AI (Bấm nút sao chép ở trên)"
        step4_subtitle = "Dán toàn bộ khối nội dung dưới đây vào ô Instructions của Custom GPT hoặc phần cài đặt System Prompt:"

        step5_title = "Giám sát thời gian thực qua Desktop Dashboard"
        step5_body = """
        <ul style="margin: 6px 0; padding-left: 20px; font-size: 12px; color: #d1dad5;">
          <li><b>Tab Nhật ký Workspace (Workspace Logs):</b> Luồng sự kiện hai pha trực tiếp qua Server-Sent Events (SSE). Quan sát ngay khi ChatGPT gọi lệnh: <code>op_started</code> &rarr; <code>op_result</code> (thời lượng ms, kết quả). Các filter nhanh: ALL, ERROR, PROCESS, FILE, SESSION.</li>
          <li><b>Tab Hoạt động GPT (GPT Activity):</b> Xem danh sách các thư mục phiên làm việc tại <code>~/Downloads/bqa-workspaces/</code>, từng lệnh shell đã thực thi, mã thoát (exit code), stdout và stderr đầy đủ.</li>
        </ul>
        """

        step6_title = "Bảng Xử lý sự cố thường gặp (Troubleshooting FAQ)"
        table_faq = f"""
        <table width="100%" cellpadding="8" cellspacing="0" class="table-faq">
          <tr>
            <th width="28%">HIỆN TƯỢNG / MÃ LỖI</th>
            <th width="32%">NGUYÊN NHÂN</th>
            <th width="40%">CÁCH KHẮC PHỤC</th>
          </tr>
          <tr>
            <td style="color: {COLORS['danger']}; font-weight: bold;">Could not connect to server / Connection refused</td>
            <td>Dịch vụ MCP hoặc Cloudflare tunnel chưa được khởi động.</td>
            <td>Vào tab <b>Runtime</b> trên desktop, bấm nút <b>Khởi động / nhận service</b> và đợi trạng thái chuyển sang <i>Ready</i>.</td>
          </tr>
          <tr>
            <td style="color: {COLORS['warning']}; font-weight: bold;">URL bị thay đổi khi restart máy</td>
            <td>Gói Cloudflare Tunnel miễn phí cấp phát subdomain ngẫu nhiên mỗi lần tạo mới tiến trình tunnel.</td>
            <td><b>Mẹo:</b> Khi sửa code hoặc file cấu hình <code>.env</code>, hãy dùng nút <b>Khởi động lại MCP bridge</b> (hoặc lệnh <code>bqa restart</code>). Nút này giữ nguyên tiến trình Tunnel và URL hiện tại, không phải đổi URL trên ChatGPT!</td>
          </tr>
          <tr>
            <td style="color: {COLORS['danger']}; font-family: monospace; font-weight: bold;">E6: BIND_REQUIRED</td>
            <td>ChatGPT quên gọi <code>host_workspace_bind</code> ở lượt đầu tiên.</td>
            <td>Nhắn một câu cho ChatGPT: <i>"Hãy gọi tool host_workspace_bind trước để gán chat_id"</i>.</td>
          </tr>
          <tr>
            <td style="color: {COLORS['warning']}; font-family: monospace; font-weight: bold;">E1: INVALID_CHAT_ID</td>
            <td>chat_id quá ngắn (&lt;6 ký tự) hoặc chứa ký tự đặc biệt không hợp lệ.</td>
            <td>chat_id phải từ 6-64 ký tự chữ, số, '.', '-', '_'. Ví dụ: <code>bqa-session-01</code>.</td>
          </tr>
          <tr>
            <td style="color: {COLORS['warning']}; font-weight: bold;">Command Blocked / Policy Denied</td>
            <td>Câu lệnh chứa các chuỗi nằm trong danh sách cấm của chế độ guarded (như rm -rf /, dd...).</td>
            <td>Dùng <code>host_check_command</code> để xem lý do cụ thể và thay thế bằng lệnh an toàn hơn.</td>
          </tr>
        </table>
        """
    else:
        hero_title = "🌐 END-TO-END INTEGRATION GUIDE FOR CHATGPT WEB"
        hero_badge = "CLOUDFLARE TUNNEL"
        hero_desc = (
            "Securely connect <b>ChatGPT Web (chatgpt.com)</b> to your local BotQuangAnh MCP server "
            "over an encrypted Cloudflare Tunnel with <b>zero router port-forwarding</b> required."
        )

        step1_title = "Start the Runtime & Copy Connector URL"
        step1_body = """
        <ol style="margin: 6px 0; padding-left: 20px;">
          <li><b>Verify runtime health:</b> In the <b>Runtime</b> tab of this desktop UI, ensure both <b>MCP bridge</b> and <b>Cloudflare tunnel</b> display green <i>running</i> status badges.</li>
          <li><b>Copy Connector URL:</b> Click <b>Copy connector URL</b> in the toolbar above, or click Copy beside Endpoint in the Runtime tab.</li>
          <li><b>Valid URL format:</b>
            <div style="margin: 6px 0; padding: 6px 10px; background-color: #151e1b; border: 1px solid #2a3632; font-family: monospace; color: #a3ff12;">
              https://&lt;random-subdomain&gt;.trycloudflare.com/mcp
            </div>
            <span style="color: #f4b942;">* IMPORTANT:</span> Valid endpoints <b>must terminate with <code>/mcp</code></b>. Do not use the bare root URL.
          </li>
        </ol>
        """

        step2_title = "Configure in ChatGPT Web (chatgpt.com)"
        step2_body = """
        <table width="100%" cellpadding="8" cellspacing="0">
          <tr>
            <td width="50%" valign="top" style="background-color: #151e1b; border: 1px solid #202b28;">
              <b style="color: #42d5ad;">OPTION A: DIRECT MCP CONNECTOR</b><br/>
              <i>(For ChatGPT Plus/Team/Enterprise accounts with Connected Apps)</i>
              <ol style="margin: 6px 0; padding-left: 18px; font-size: 12px; color: #d1dad5;">
                <li>Sign in to <a href="https://chatgpt.com">chatgpt.com</a>.</li>
                <li>Open <b>Settings</b> &rarr; <b>Connected Apps</b> (or Developer &rarr; MCP Servers).</li>
                <li>Click <b>Add MCP Server</b>:
                  <ul style="padding-left: 14px; margin-top: 4px;">
                    <li><b>Name:</b> BotQuangAnh MCP</li>
                    <li><b>URL:</b> Paste endpoint with <code>/mcp</code></li>
                    <li><b>Transport:</b> Streamable HTTP</li>
                    <li><b>Auth:</b> None (or Bearer Token if REQUIRE_AUTH=true)</li>
                  </ul>
                </li>
                <li>Click <b>Connect / Save</b>. ChatGPT discovers all 17 tools automatically.</li>
              </ol>
            </td>
            <td width="50%" valign="top" style="background-color: #17221f; border: 1px solid #2a3d36;">
              <b style="color: #a3ff12;">OPTION B: CUSTOM GPT (RECOMMENDED ⭐)</b><br/>
              <i>(Best operational consistency with pinned System Instructions)</i>
              <ol style="margin: 6px 0; padding-left: 18px; font-size: 12px; color: #d1dad5;">
                <li>Navigate to <a href="https://chatgpt.com/gpts/editor">chatgpt.com/gpts/editor</a>.</li>
                <li>In <b>Configure</b>:
                  <ul style="padding-left: 14px; margin-top: 4px;">
                    <li><b>Name:</b> BotQuangAnh Host Assistant</li>
                    <li><b>Instructions:</b> Paste the <b>Prompt Template</b> from Step 4.</li>
                  </ul>
                </li>
                <li>In <b>Actions / MCP Connectors</b>:
                  <ul style="padding-left: 14px; margin-top: 4px;">
                    <li>Add connector targeting your <code>/mcp</code> URL.</li>
                  </ul>
                </li>
                <li>Save GPT with <b>Only me</b> visibility.</li>
              </ol>
            </td>
          </tr>
        </table>
        """

        step3_title = "Mandatory 3-Step Handshake Protocol"
        step3_body = """
        <div style="background-color: #241a10; border: 1px solid #5a3d1b; padding: 8px 10px; margin-bottom: 8px;">
          <b style="color: #f4b942;">MANDATORY STEP 1: PER-CHAT WORKSPACE BINDING</b><br/>
          In every conversation, the VERY FIRST call ChatGPT makes MUST be:<br/>
          <div style="margin: 6px 0; padding: 6px; background-color: #0e1513; border: 1px solid #3a4a44; font-family: monospace; color: #a3ff12;">
            host_workspace_bind(chat_id="bqa-session-xxxxx")
          </div>
          <span style="color: #ff6b61; font-weight: bold;">WARNING:</span> Calling any other tool prior to binding triggers an immediate <b>E6 (BIND_REQUIRED)</b> rejection!
        </div>
        <div style="font-size: 12px; color: #d1dad5; line-height: 1.6;">
          <b>STEP 2: ENVIRONMENT DISCOVERY:</b><br/>
          &bull; Call <code>host_knowledge(section="overview")</code> to inspect workspace boundaries and policies.<br/>
          &bull; Call <code>host_knowledge(section="tools", query="&lt;tool&gt;")</code> to verify binary availability before running commands.<br/><br/>
          <b>STEP 3: GUARDED EXECUTION:</b><br/>
          &bull; Check command safety first: <code>host_check_command(command="...")</code>.<br/>
          &bull; Run commands safely: <code>host_run_command(command="...", cwd="...")</code>.<br/>
          &bull; Apply surgical modifications: Always prefer <code>host_replace_in_file</code> over full overwrites.<br/>
          &bull; Persist durable notes: <code>host_save_note(title="...", content="...")</code>.
        </div>
        """

        step4_title = "System Instructions Prompt Template (Click Copy Prompt button above)"
        step4_subtitle = "Paste this block into the Instructions field of your Custom GPT or System Prompt configuration:"

        step5_title = "Real-Time Observability via Desktop UI"
        step5_body = """
        <ul style="margin: 6px 0; padding-left: 20px; font-size: 12px; color: #d1dad5;">
          <li><b>Workspace Logs tab:</b> Real-time two-phase event streaming via Server-Sent Events (SSE). Track operation lifecycles live: <code>op_started</code> &rarr; <code>op_result</code> (latency ms, outcome). Filter chips: ALL, ERROR, PROCESS, FILE, SESSION.</li>
          <li><b>GPT Activity tab:</b> Audit per-chat workspace folders in <code>~/Downloads/bqa-workspaces/</code>, view every shell command executed, exit codes, and full stdout/stderr streams.</li>
        </ul>
        """

        step6_title = "Troubleshooting Common Issues (FAQ)"
        table_faq = f"""
        <table width="100%" cellpadding="8" cellspacing="0" class="table-faq">
          <tr>
            <th width="28%">SYMPTOM / ERROR</th>
            <th width="32%">ROOT CAUSE</th>
            <th width="40%">RESOLUTION</th>
          </tr>
          <tr>
            <td style="color: {COLORS['danger']}; font-weight: bold;">Could not connect to server / Connection refused</td>
            <td>Host MCP bridge or Cloudflare tunnel process is inactive.</td>
            <td>Navigate to <b>Runtime</b> tab and click <b>Start / adopt service</b>. Wait until status shows <i>Ready</i>.</td>
          </tr>
          <tr>
            <td style="color: {COLORS['warning']}; font-weight: bold;">Tunnel URL changes on restart</td>
            <td>Ephemeral Cloudflare tunnels generate random domains when restarted from scratch.</td>
            <td><b>Pro Tip:</b> When updating code or <code>.env</code>, click <b>Restart MCP bridge</b> (or <code>bqa restart</code>). This restarts Python while keeping the tunnel alive, preserving your ChatGPT URL!</td>
          </tr>
          <tr>
            <td style="color: {COLORS['danger']}; font-family: monospace; font-weight: bold;">E6: BIND_REQUIRED</td>
            <td>ChatGPT attempted a tool call without binding a chat_id first.</td>
            <td>Send a prompt to ChatGPT: <i>"Please call host_workspace_bind first to initialize a session."</i></td>
          </tr>
          <tr>
            <td style="color: {COLORS['warning']}; font-family: monospace; font-weight: bold;">E1: INVALID_CHAT_ID</td>
            <td>chat_id is too short (&lt;6 characters) or contains forbidden characters.</td>
            <td>Use 6-64 alphanumeric characters matching [a-zA-Z0-9._-], e.g. <code>bqa-session-01</code>.</td>
          </tr>
          <tr>
            <td style="color: {COLORS['warning']}; font-weight: bold;">Command Blocked / Policy Denied</td>
            <td>Command violated guarded execution rules (e.g. destructive commands).</td>
            <td>Use <code>host_check_command</code> to inspect the policy denial reason and select a safe alternative.</td>
          </tr>
        </table>
        """

    return f"""<!DOCTYPE html>
<html>
<head><style>{css}</style></head>
<body>

<!-- HERO CARD -->
<table width="100%" cellpadding="12" cellspacing="0" class="hero-card">
  <tr>
    <td>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td class="hero-title">{hero_title}</td>
          <td align="right"><span class="hero-badge">{hero_badge}</span></td>
        </tr>
      </table>
      <div class="hero-desc">{hero_desc}</div>
    </td>
  </tr>
</table>

<!-- STEP 1 -->
<table width="100%" cellpadding="10" cellspacing="0" class="step-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <span class="step-badge">01</span> &nbsp;
      <span class="step-title">{step1_title}</span>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 8px;">
      {step1_body}
    </td>
  </tr>
</table>

<!-- STEP 2 -->
<table width="100%" cellpadding="10" cellspacing="0" class="step-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <span class="step-badge">02</span> &nbsp;
      <span class="step-title">{step2_title}</span>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 8px;">
      {step2_body}
    </td>
  </tr>
</table>

<!-- STEP 3 -->
<table width="100%" cellpadding="10" cellspacing="0" class="step-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <span class="step-badge">03</span> &nbsp;
      <span class="step-title">{step3_title}</span>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 8px;">
      {step3_body}
    </td>
  </tr>
</table>

<!-- STEP 4 -->
<table width="100%" cellpadding="10" cellspacing="0" class="step-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <span class="step-badge">04</span> &nbsp;
      <span class="step-title">{step4_title}</span>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 8px;">
      <div style="color: {COLORS['muted']}; font-size: 12px; margin-bottom: 8px;">{step4_subtitle}</div>
      <div class="prompt-box"><pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word;">{prompt_text}</pre></div>
    </td>
  </tr>
</table>

<!-- STEP 5 -->
<table width="100%" cellpadding="10" cellspacing="0" class="step-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <span class="step-badge">05</span> &nbsp;
      <span class="step-title">{step5_title}</span>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 8px;">
      {step5_body}
    </td>
  </tr>
</table>

<!-- STEP 6 -->
<table width="100%" cellpadding="10" cellspacing="0" class="step-card">
  <tr>
    <td style="border-bottom: 1px solid {COLORS['border_subtle']};">
      <span class="step-badge">06</span> &nbsp;
      <span class="step-title">{step6_title}</span>
    </td>
  </tr>
  <tr>
    <td style="padding-top: 8px;">
      {table_faq}
    </td>
  </tr>
</table>

</body>
</html>"""
