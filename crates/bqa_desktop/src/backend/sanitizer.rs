use std::process::Command;

pub fn copy_to_system_clipboard(text: &str) {
    use std::io::Write;
    if let Ok(mut child) = Command::new("xclip")
        .args(["-selection", "clipboard"])
        .stdin(std::process::Stdio::piped())
        .spawn()
    {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
        return;
    }
    if let Ok(mut child) = Command::new("wl-copy")
        .stdin(std::process::Stdio::piped())
        .spawn()
    {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
        return;
    }
    if let Ok(mut child) = Command::new("xsel")
        .args(["--clipboard", "--input"])
        .stdin(std::process::Stdio::piped())
        .spawn()
    {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
    }
}

pub fn sanitize_honeypot_text(text: &str) -> String {
    let lower = text.to_lowercase();
    if !lower.contains("x-llm")
        && !lower.contains("honeypot")
        && !lower.contains("canary")
        && !lower.contains("honey-port")
        && !lower.contains("antigravity")
        && !lower.contains("agent:")
        && !lower.contains("agent=")
        && !lower.contains("model:")
        && !lower.contains("model=")
    {
        return text.to_string();
    }
    let mut out = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        let trimmed_lower = trimmed.to_lowercase();
        // Entire line is solely a honeypot/canary directive
        if trimmed_lower.starts_with("x-llm-")
            || trimmed_lower.starts_with("# x-llm-")
            || trimmed_lower.starts_with("// x-llm-")
            || trimmed_lower.starts_with("/* x-llm-")
            || trimmed_lower.starts_with("<!-- x-llm-")
            || trimmed_lower.starts_with("prompt-canary:")
            || trimmed_lower.starts_with("agent_name:")
        {
            continue;
        }

        // In-place inline comment / honeypot redaction
        let mut cleaned_line = line.to_string();

        // 1. Redact trailing inline comments
        for delimiter in &[
            " # x-llm-",
            " // x-llm-",
            " # canary",
            " // canary",
            " # honey-port",
            " // honey-port",
        ] {
            if let Some(pos) = cleaned_line.to_lowercase().find(delimiter) {
                cleaned_line.truncate(pos);
            }
        }

        // 2. Redact standalone bracketed tags like [antigravity]
        if let Some(pos) = cleaned_line.to_lowercase().find("[antigravity]") {
            cleaned_line = format!("{}{}", &cleaned_line[..pos], &cleaned_line[pos + 13..]);
        }

        let final_line = cleaned_line.trim_end();
        if !final_line.is_empty() {
            out.push(final_line.to_string());
        }
    }
    out.join("\n")
}
