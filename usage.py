#!/usr/bin/python3
"""Persistent local receiver for Codex subscription-limit notifications."""
import json
import shutil
import subprocess
import threading


class UsageClient:
    """Receive account/rateLimits/updated without querying current limits."""

    def __init__(self, on_update=None):
        self.on_update = on_update
        self.process = None
        self._pending = {}
        self._lock = threading.RLock()
        self._next_id = 1

    @property
    def connected(self):
        return self.process is not None and self.process.poll() is None

    def connect(self):
        if self.connected:
            return
        binary = shutil.which('codex') or '/usr/lib/chatgpt/resources/codex'
        self.process = subprocess.Popen(
            [binary, 'app-server', '--stdio'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        threading.Thread(target=self._read_messages, daemon=True).start()
        self._request('initialize', {
            'clientInfo': {'name': 'codex_usage_topbar', 'version': '1.1.0'},
        })
        self._send({'method': 'initialized', 'params': {}})

    def close(self):
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def _request(self, method, params=None, timeout=25):
        if not self.connected:
            raise RuntimeError('Codex app-server is not running')
        response = threading.Event()
        result = []
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = (response, result)
            self._send({'id': request_id, 'method': method, 'params': params or {}})
        if not response.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise TimeoutError('Timed out while connecting to local Codex')
        with self._lock:
            self._pending.pop(request_id, None)
        message = result[0]
        if 'error' in message:
            raise RuntimeError('Codex returned an error while reading usage')
        return message['result']

    def _send(self, message):
        with self._lock:
            if not self.connected:
                raise RuntimeError('Codex app-server is not running')
            self.process.stdin.write((json.dumps(message) + '\n').encode())
            self.process.stdin.flush()

    def _read_messages(self):
        try:
            for raw_line in self.process.stdout:
                message = json.loads(raw_line)
                if 'id' in message:
                    with self._lock:
                        response = self._pending.get(message['id'])
                    if response:
                        event, result = response
                        result.append(message)
                        event.set()
                elif message.get('method') == 'account/rateLimits/updated' and self.on_update:
                    self.on_update(message.get('params', {}).get('rateLimits'))
        except (OSError, ValueError):
            pass
if __name__ == '__main__':
    client = UsageClient()
    try:
        client.connect()
        print(json.dumps({'status': 'connected'}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    finally:
        client.close()
