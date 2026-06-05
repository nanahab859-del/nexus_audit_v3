import argparse
from aiohttp import web
from api.server import create_app

def main() -> None:
    parser = argparse.ArgumentParser(description="Nexus Audit V3 Server")
    parser.add_argument("--port", type=int, default=8421, help="Port to listen on")
    args = parser.parse_args()

    app = create_app()

    print(f"Starting Nexus Audit V3 on http://127.0.0.1:{args.port}")
    web.run_app(app, host="127.0.0.1", port=args.port)

if __name__ == "__main__":
    main()
