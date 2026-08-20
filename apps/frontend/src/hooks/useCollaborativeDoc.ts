import { useEffect, useRef, useState, useCallback } from 'react';
import * as Y from 'yjs';

type WsStatus = 'Disconnected' | 'Connecting...' | 'Live';

interface UseCollaborativeDocResult {
  docText: string;
  setDocText: (newText: string) => void;
  wsStatus: WsStatus;
  onlineCount: number;
  manualSave: () => Promise<void>;
  saveStatus: string;
  setSaveStatus: (s: string) => void;
}

const uint8ToBase64 = (buf: Uint8Array): string => {
  let binary = '';
  for (let i = 0; i < buf.byteLength; i++) binary += String.fromCharCode(buf[i]);
  return btoa(binary);
};

const base64ToUint8 = (b64: string): Uint8Array => {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
};

export function useCollaborativeDoc(
  docId: string,
  workspaceId: string,
  token: string
): UseCollaborativeDocResult {
  const wsRef = useRef<WebSocket | null>(null);
  const ydocRef = useRef<Y.Doc | null>(null);
  const ytextRef = useRef<Y.Text | null>(null);

  const [docText, setDocTextState] = useState('');
  const [wsStatus, setWsStatus] = useState<WsStatus>('Disconnected');
  const [onlineCount, setOnlineCount] = useState(1);
  const [saveStatus, setSaveStatus] = useState('Saved');

  useEffect(() => {
    if (!docId || !token) return;

    if (wsRef.current) {
      wsRef.current.onmessage = null;
      wsRef.current.close();
    }

    const ydoc = new Y.Doc();
    const ytext = ydoc.getText('content');
    ydocRef.current = ydoc;
    ytextRef.current = ytext;

    const observer = () => setDocTextState(ytext.toString());
    ytext.observe(observer);

    setWsStatus('Connecting...');
    // Vercel does not support WebSocket proxying via vercel.json.
    // In production, we must connect directly to the Render backend.
    const backendUrl = import.meta.env.VITE_BACKEND_URL;
    let wsUrl;
    if (backendUrl) {
      // e.g. VITE_BACKEND_URL = "https://collabspace-backend-c26l.onrender.com"
      const wsHost = backendUrl.replace(/^http/, 'ws');
      wsUrl = `${wsHost}/realtime/ws?token=${encodeURIComponent(token)}`;
    } else {
      // Fallback for local development using Vite proxy
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      wsUrl = `${wsProtocol}//${window.location.host}/realtime/ws?token=${encodeURIComponent(token)}`;
    }
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('Live');
      ws.send(JSON.stringify({ type: 'join_room', room_id: docId }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === 'sync_step_1' && Array.isArray(msg.updates)) {
          ydoc.transact(() => {
            for (const b64 of msg.updates) {
              try { Y.applyUpdate(ydoc, base64ToUint8(b64)); } catch {}
            }
          });
          if (workspaceId) {
            ws.send(JSON.stringify({
              type: 'presence_update',
              room_id: `workspace_${workspaceId}`,
              status: 'online'
            }));
          }
        }

        if (msg.type === 'doc_update' && msg.update) {
          Y.applyUpdate(ydoc, base64ToUint8(msg.update), 'remote');
        }

        if (msg.type === 'presence_update') {
          setOnlineCount(prev =>
            msg.status === 'online' ? Math.min(prev + 1, 99) : Math.max(prev - 1, 1)
          );
        }
      } catch {}
    };

    ws.onerror = () => setWsStatus('Disconnected');
    ws.onclose = () => setWsStatus('Disconnected');

    const updateHandler = (update: Uint8Array, origin: unknown) => {
      if (origin === 'remote') return;
      if (ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({
        type: 'doc_update',
        room_id: docId,
        update: uint8ToBase64(update)
      }));
    };
    ydoc.on('update', updateHandler);

    const heartbeatInterval = workspaceId
      ? setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'heartbeat', room_id: `workspace_${workspaceId}` }));
          }
        }, 10_000)
      : null;

    return () => {
      ytext.unobserve(observer);
      ydoc.off('update', updateHandler);
      if (heartbeatInterval) clearInterval(heartbeatInterval);
      ws.onmessage = null;
      ws.close();
      ydoc.destroy();
    };
  }, [docId, token, workspaceId]);

  const setDocText = useCallback((newText: string) => {
    const ydoc = ydocRef.current;
    const ytext = ytextRef.current;
    if (!ydoc || !ytext) return;
    ydoc.transact(() => {
      const current = ytext.toString();
      if (current === newText) return;
      ytext.delete(0, current.length);
      ytext.insert(0, newText);
    });
  }, []);

  const manualSave = useCallback(async () => {
    if (!docId || !token || !workspaceId) return;
    setSaveStatus('Saving...');
    try {
      await fetch(`/api/documents/${workspaceId}/${docId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: ytextRef.current?.toString() ?? '' })
      });
      setSaveStatus('Saved');
    } catch {
      setSaveStatus('Error saving');
    }
  }, [docId, token, workspaceId]);

  return { docText, setDocText, wsStatus, onlineCount, manualSave, saveStatus, setSaveStatus };
}
