# Connection Contract

## MoruBridge

Build with the Paper bootstrap JAR from the target server. The helper finds the matching API and dependency jars in that server's `libraries/` directory.

```bash
python3 scripts/build_moru_bridge.py \
  --paper-jar /path/to/server/paper-<version>.jar \
  --output /tmp/MoruBridge.jar
```

Copy the resulting JAR to the server's `plugins/` directory and start the server once. It creates `plugins/MoruBridge/config.yml` then disables itself until `auth-token` is replaced with a fresh secret of at least 24 characters. Restart after changing that value.

Required plugin configuration:

```yaml
bind-host: "127.0.0.1"
port: 25576
auth-token: "a-fresh-private-token"
```

`bind-host` must resolve to a loopback address. The plugin refuses all other addresses and never logs the token. Do not put the token in the Codex profile; export it to the variable named by `bridge.token_env` instead.

## MSMP

MoruBridge is for player conversation. Minecraft Server Management Protocol (MSMP) is separate and is only necessary for standard administrator operations.

For a same-host or tunnel-only setup, use an explicit localhost port and a newly rotated secret in `server.properties`:

```properties
management-server-enabled=true
management-server-host=127.0.0.1
management-server-port=25585
management-server-secret=<fresh-private-token>
management-server-tls-enabled=false
```

Disabling TLS is only acceptable while the management service remains loopback-only. For any other topology, retain loopback binding and use an encrypted SSH or VPN tunnel; never bind either MoruBridge or MSMP to a public interface.

Restart the server after changing `server.properties`. Do not reuse a token that has appeared in a terminal transcript or shared document.

## Client Profile

Create the profile with `init-profile`, fill in non-secret endpoints and paths, then export the two token variables before use.

```toml
[bridge]
url = "http://127.0.0.1:25576"
token_env = "MORU_BRIDGE_TOKEN"

[msmp]
url = "ws://127.0.0.1:25585"
token_env = "MORU_MSMP_TOKEN"

[context]
server_root = "/path/to/server"
guide_paths = ["/path/to/server-guide.md"]
```

The profile contains no secret values. `snapshot` exposes only a fixed allowlist of non-secret server properties and installed plugin filenames.
