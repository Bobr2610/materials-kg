⠀                                       
█▀▄▀█ █ █▄ ▄█ █▀▀█ █▀▀ █▀▀█ █▀▀▄ █▀▀▀
█ ▀ █ █ █ ▀ █ █  █ █   █  █ █  █ █▀▀ 
▀   ▀ ▀ ▀   ▀ ▀▀▀▀ ▀▀▀ ▀▀▀▀ ▀▀▀  ▀▀▀▀
System.Management.Automation.RemoteException
Commands:
  mimo completion          generate shell completion script
  mimo acp                 start ACP (Agent Client Protocol) server
  mimo mcp                 manage MCP (Model Context Protocol) servers
  mimo [project]           start mimocode tui                                              [default]
  mimo attach <url>        attach to a running mimocode server
  mimo run [message..]     run mimocode with a message
  mimo debug               debugging and troubleshooting tools
  mimo providers           manage AI providers and credentials                       [aliases: auth]
  mimo agent               manage agents
  mimo upgrade [target]    upgrade mimocode to the latest or a specific version
  mimo uninstall           uninstall mimocode and remove all related files
  mimo serve               starts a headless mimocode server
  mimo models [provider]   list all available models
  mimo stats               show token usage and cost statistics
  mimo export [sessionID]  export session data as JSON
  mimo import <file>       import session data from JSON file or URL
  mimo github              manage GitHub agent
  mimo pr <number>         fetch and checkout a GitHub PR branch, then run mimocode
  mimo session             manage sessions
  mimo plugin <module>     install plugin and update config                          [aliases: plug]
  mimo db                  database tools
System.Management.Automation.RemoteException
Positionals:
  project  path to start mimocode in                                                        [string]
System.Management.Automation.RemoteException
Options:
  -h, --help         show help                                                             [boolean]
  -v, --version      show version number                                                   [boolean]
      --print-logs   print logs to stderr                                                  [boolean]
      --log-level    log level                  [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure         run without external plugins                                          [boolean]
      --port         port to listen on                                         [number] [default: 0]
      --hostname     hostname to listen on                           [string] [default: "127.0.0.1"]
      --mdns         enable mDNS service discovery (defaults hostname to 0.0.0.0)
                                                                          [boolean] [default: false]
      --mdns-domain  custom domain name for mDNS service (default: mimocode.local)
                                                                [string] [default: "mimocode.local"]
      --cors         additional domains to allow for CORS                      [array] [default: []]
      --no-auth      allow starting without authentication on non-loopback addresses (DANGEROUS)
                                                                          [boolean] [default: false]
  -m, --model        model to use in the format of provider/model                           [string]
  -c, --continue     continue the last session                                             [boolean]
  -s, --session      session id to continue                                                 [string]
      --fork         fork the session when continuing (use with --continue or --session)   [boolean]
      --prompt       prompt to use                                                          [string]
      --agent        agent to use                                                           [string]
      --never-ask    start in never-ask mode — auto-decide without asking (permissions excluded),
                     toggle at runtime with /never-ask                    [boolean] [default: false]
      --trust        skip workspace trust prompt and trust the directory  [boolean] [default: false]
