import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the verifiable agent runtime API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    arguments = parser.parse_args()
    uvicorn.run(
        "verifiable_agent_runtime.api:app",
        host=arguments.host,
        port=arguments.port,
    )


if __name__ == "__main__":
    main()
