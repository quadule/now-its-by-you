# Hosting the studio yourself

A recipe for running the public studio (`songbird studio --public`) on a server of your own: a container reached
through a Cloudflare Tunnel, with no port opened on the host. docker-compose.yml says how to start it, and
studio.env.example what to set; docs/history/web-studio-server-plan.md explains each setting.

It is not what studio.itsby.you runs. Since September 30, 2026 that studio runs entirely in the visitor's browser,
as static files on Cloudflare (web/studio-wasm/tools/build_site.py, web/studio-site/).
