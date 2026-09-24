use std::sync::Arc;
use bqa_core::backend::paths::AppPaths;
use bqa_core::db::Database;
use bqa_core::mcp::run_stdio_server;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let paths = Arc::new(AppPaths::new());
    let db = Arc::new(Database::open(&paths.db_path)?);

    run_stdio_server(paths, db).await
}
