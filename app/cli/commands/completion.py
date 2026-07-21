from __future__ import annotations

from app.cli.context import CLIContext


_COMMANDS = "start stop restart status url server health capabilities fs cmd knowledge logs config doctor completion version"


def generate(shell: str) -> str:
    if shell == "bash":
        return f'''_bqa_complete() {{
    local cur prev
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    case "$prev" in
        server) COMPREPLY=( $(compgen -W "restart status" -- "$cur") ); return ;;
        fs) COMPREPLY=( $(compgen -W "ls cat write append replace mkdir search" -- "$cur") ); return ;;
        cmd) COMPREPLY=( $(compgen -W "check run" -- "$cur") ); return ;;
        knowledge) COMPREPLY=( $(compgen -W "overview guide tools search all" -- "$cur") ); return ;;
        config) COMPREPLY=( $(compgen -W "show get path validate" -- "$cur") ); return ;;
        completion) COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") ); return ;;
        logs) COMPREPLY=( $(compgen -W "server tunnel launcher audit follow" -- "$cur") ); return ;;
    esac
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "{_COMMANDS}" -- "$cur") )
    fi
}}
complete -F _bqa_complete bqa
'''
    if shell == "zsh":
        return f'''#compdef bqa
_arguments '1:command:({ _COMMANDS })' '*::arg:->args'
case $words[2] in
  server) _values 'server command' restart status ;;
  fs) _values 'fs command' ls cat write append replace mkdir search ;;
  cmd) _values 'cmd command' check run ;;
  knowledge) _values 'knowledge command' overview guide tools search all ;;
  config) _values 'config command' show get path validate ;;
  completion) _values 'shell' bash zsh fish ;;
esac
'''.replace("{ _COMMANDS }", _COMMANDS)
    return f'''complete -c bqa -f
complete -c bqa -n '__fish_use_subcommand' -a '{_COMMANDS}'
complete -c bqa -n '__fish_seen_subcommand_from server' -a 'restart status'
complete -c bqa -n '__fish_seen_subcommand_from fs' -a 'ls cat write append replace mkdir search'
complete -c bqa -n '__fish_seen_subcommand_from cmd' -a 'check run'
complete -c bqa -n '__fish_seen_subcommand_from knowledge' -a 'overview guide tools search all'
complete -c bqa -n '__fish_seen_subcommand_from config' -a 'show get path validate'
complete -c bqa -n '__fish_seen_subcommand_from completion' -a 'bash zsh fish'
'''


def handle_completion(_ctx: CLIContext, args) -> int:
    print(generate(args.shell), end="")
    return 0
