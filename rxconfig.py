import reflex as rx

config = rx.Config(
    app_name="sqllm",
    frontend_path="/SQLLM",  # Base path for the frontend
    api_url="https://sbaai.sbasite.com/SQLLM_API",  # Update with your backend URL
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)
