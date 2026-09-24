use std::sync::Arc;
use std::thread;

use notify::{Config, RecommendedWatcher, RecursiveMode, Watcher};
use tao::{
    dpi::LogicalSize,
    event::{Event, StartCause, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder},
    platform::unix::WindowExtUnix,
    window::WindowBuilder,
};
use wry::{WebViewBuilder, WebViewBuilderExtUnix};

use crate::backend::ipc::{handle_ipc_message, IpcMessage};
use crate::backend::paths::AppPaths;
use crate::db::Database;

#[derive(Debug, Clone)]
pub enum UserEvent {
    EvalScript(String),
}

pub fn run_app(paths: Arc<AppPaths>, db: Arc<Database>) -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(unix)]
    unsafe {
        libc::signal(libc::SIGHUP, libc::SIG_IGN);
    }

    let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    // Background inotify watcher for instant live stream updates
    let proxy_watcher = proxy.clone();
    let paths_watcher = Arc::clone(&paths);
    thread::spawn(move || {
        let (tx, rx) = std::sync::mpsc::channel();
        let mut watcher = match RecommendedWatcher::new(tx, Config::default()) {
            Ok(w) => w,
            Err(_) => return,
        };

        let logs_dir = paths_watcher.repo_root.join("logs");
        let ws_dir = paths_watcher.workspace_root.clone();

        if logs_dir.exists() {
            let _ = watcher.watch(&logs_dir, RecursiveMode::NonRecursive);
        }
        if ws_dir.exists() {
            let _ = watcher.watch(&ws_dir, RecursiveMode::Recursive);
        }

        let mut last_trigger = std::time::Instant::now();
        for event in rx.into_iter().flatten() {
            if (event.kind.is_modify() || event.kind.is_create())
                && last_trigger.elapsed() >= std::time::Duration::from_millis(150)
            {
                last_trigger = std::time::Instant::now();
                let js = "if (window.__triggerFastPoll) window.__triggerFastPoll();".to_string();
                let _ = proxy_watcher.send_event(UserEvent::EvalScript(js));
            }
        }
    });

    let window = WindowBuilder::new()
        .with_title("BQA Bridge Center — Native Studio Console")
        .with_inner_size(LogicalSize::new(1280.0, 800.0))
        .with_min_inner_size(LogicalSize::new(960.0, 600.0))
        .build(&event_loop)?;

    let html_content = include_str!("../../ui/index.html");

    let paths_clone = Arc::clone(&paths);
    let db_clone = Arc::clone(&db);
    let proxy_clone = proxy.clone();

    let enable_devtools =
        std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) || cfg!(debug_assertions);

    let builder = WebViewBuilder::new()
        .with_devtools(enable_devtools)
        .with_html(html_content)
        .with_ipc_handler(move |req: wry::http::Request<String>| {
            let msg = req.body();
            if let Ok(parsed) = serde_json::from_str::<IpcMessage>(msg) {
                let p = Arc::clone(&paths_clone);
                let d = Arc::clone(&db_clone);
                let pr = proxy_clone.clone();

                thread::spawn(move || {
                    handle_ipc_message(parsed, &p, &d, &pr);
                });
            }
        });

    let vbox = window
        .default_vbox()
        .expect("Failed to get default vbox container on Linux GTK");
    let webview = builder.build_gtk(vbox)?;

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::NewEvents(StartCause::Init) => {
                if std::env::var("BQA_DEBUG").map(|v| v == "1").unwrap_or(false) {
                    println!("[+] BQA Rust Native Desktop App Initialized successfully");
                }
            }
            Event::UserEvent(UserEvent::EvalScript(script)) => {
                let _ = webview.evaluate_script(&script);
            }
            Event::WindowEvent {
                event: WindowEvent::CloseRequested,
                ..
            } => {
                *control_flow = ControlFlow::Exit;
            }
            _ => (),
        }
    });
}
