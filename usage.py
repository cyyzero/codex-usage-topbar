#!/usr/bin/python3
"""Read Codex subscription limits through the local Codex app-server."""
import json
import os
import selectors
import shutil
import subprocess
import time


def read_usage(timeout=25):
    """Return the Codex rate-limit bucket for the signed-in account."""
    binary = shutil.which('codex') or '/usr/lib/chatgpt/resources/codex'
    process = subprocess.Popen(
        [binary, 'app-server', '--stdio'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b''
    deadline = time.monotonic() + timeout

    def send(message):
        process.stdin.write((json.dumps(message) + '\n').encode())
        process.stdin.flush()

    def receive(identifier):
        nonlocal buffer
        while time.monotonic() < deadline:
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                message = json.loads(line)
                if message.get('id') == identifier:
                    if 'error' in message:
                        raise RuntimeError('Codex returned an error while reading usage')
                    return message['result']
            if selector.select(max(0, deadline - time.monotonic())):
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError('Codex app-server exited; check the Codex sign-in')
                buffer += chunk
        raise TimeoutError('Timed out while reading Codex usage')

    try:
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'codex_usage_topbar', 'version': '1.0.0'},
        }})
        receive(1)
        send({'method': 'initialized', 'params': {}})
        send({'id': 2, 'method': 'account/rateLimits/read'})
        result = receive(2)
        limits = (result.get('rateLimitsByLimitId') or {}).get('codex')
        limits = limits or result.get('rateLimits')
        if not limits:
            raise RuntimeError('The current account did not return Codex limits')
        return limits
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdin.close()
        process.stdout.close()


if __name__ == '__main__':
    try:
        print(json.dumps(read_usage(), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
