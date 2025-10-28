import reflex as rx


def isProd() -> bool:
    return rx.config.EnvironmentVariables.REFLEX_ENV_MODE.get() == rx.constants.Env.PROD


config = rx.Config(
    app_name="sqllm",
    frontend_path="/SQLLM",
    api_url="https://sbaai.sbasite.com/SQLLM_API"
    if isProd()
    else "http://0.0.0.0:8000",  # Update with your backend URL
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)
