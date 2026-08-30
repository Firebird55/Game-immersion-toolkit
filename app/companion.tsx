'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Crosshair,
  Database,
  Pause,
  Play,
  Radio,
  RefreshCw,
  ScanLine,
  Settings2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const API_URL = 'http://127.0.0.1:8766';
const WS_URL = 'ws://127.0.0.1:8766/api/ws';

type CaptureRegion = { left: number; top: number; width: number; height: number };
type Settings = {
  process_names: string[];
  window_title_contains: string[];
  region: CaptureRegion;
  scan_interval_ms: number;
  stable_frames: number;
  fuzzy_threshold: number;
  auto_start: boolean;
  save_unmatched: boolean;
};
type CaptureStatus = {
  running: boolean;
  phase: string;
  message: string;
  window_title: string | null;
  window_bounds: [number, number, number, number] | null;
  crop_bounds: [number, number, number, number] | null;
  last_ocr: string;
  last_ocr_confidence: number | null;
  last_match_score: number | null;
  last_scan_at: string | null;
  last_error: string | null;
};
type TextMapStatus = { ready: boolean; state: string; message: string; entry_count: number };
type TranscriptLine = {
  id: number;
  created_at: string;
  session_id: string;
  source_ocr: string;
  english: string;
  chinese: string;
  text_id: string;
  score: number;
  match_kind: string;
  ambiguous: boolean;
};
type StatusPayload = {
  capture: CaptureStatus;
  textmaps: TextMapStatus;
  settings: Settings;
  session: { id: string; line_count: number; total_line_count: number };
};

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

function phaseLabel(phase: string) {
  const labels: Record<string, string> = {
    starting: 'Starting',
    waiting_for_game: 'Waiting for game',
    loading_textmaps: 'Loading TextMaps',
    listening: 'Listening',
    unmatched: 'Reading subtitle',
    matched: 'Matched',
    error: 'Retrying',
    stopped: 'Paused',
  };
  return labels[phase] ?? phase.replaceAll('_', ' ');
}

export function Companion() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [online, setOnline] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftSettings, setDraftSettings] = useState<Settings | null>(null);
  const [previewTick, setPreviewTick] = useState(0);
  const [saving, setSaving] = useState(false);
  const [refreshingMaps, setRefreshingMaps] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadSnapshot = useCallback(async () => {
    try {
      const [statusResponse, linesResponse] = await Promise.all([
        fetch(`${API_URL}/api/status`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/lines?limit=500`, { cache: 'no-store' }),
      ]);
      if (!statusResponse.ok || !linesResponse.ok) throw new Error('Companion service unavailable');
      const nextStatus = (await statusResponse.json()) as StatusPayload;
      setStatus(nextStatus);
      setDraftSettings(nextStatus.settings);
      setLines((await linesResponse.json()) as TranscriptLine[]);
      setOnline(true);
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    loadSnapshot();
    const poll = window.setInterval(loadSnapshot, 10000);
    return () => window.clearInterval(poll);
  }, [loadSnapshot]);

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | null = null;

    const connect = () => {
      socket = new WebSocket(WS_URL);
      socket.onopen = () => setOnline(true);
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data);
        if (event.type === 'snapshot') {
          setStatus(event.snapshot);
          setDraftSettings(event.snapshot.settings);
        }
        if (event.type === 'capture_status') {
          setStatus((current) => current ? { ...current, capture: event.capture } : current);
        }
        if (event.type === 'textmaps_status') {
          setRefreshingMaps(false);
          setStatus((current) => current ? { ...current, textmaps: event.textmaps } : current);
        }
        if (event.type === 'settings') {
          setDraftSettings(event.settings);
          setStatus((current) => current ? { ...current, settings: event.settings } : current);
        }
        if (event.type === 'line') {
          const line = event.line as TranscriptLine;
          setLines((current) => current.some((item) => item.id === line.id)
            ? current
            : [line, ...current].slice(0, 500));
          setStatus((current) => current ? {
            ...current,
            session: {
              ...current.session,
              line_count: current.session.line_count + 1,
              total_line_count: current.session.total_line_count + 1,
            },
          } : current);
        }
      };
      socket.onclose = () => {
        setOnline(false);
        if (!closed) reconnectTimer.current = setTimeout(connect, 1500);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      closed = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (!settingsOpen) return;
    setPreviewTick(Date.now());
    const timer = window.setInterval(() => setPreviewTick(Date.now()), 1100);
    return () => window.clearInterval(timer);
  }, [settingsOpen]);

  const latestLine = lines[0] ?? null;
  const sessionLines = useMemo(
    () => lines.filter((line) => !status || line.session_id === status.session.id),
    [lines, status],
  );

  async function toggleCapture() {
    if (!status) return;
    const action = status.capture.running ? 'stop' : 'start';
    await fetch(`${API_URL}/api/capture/${action}`, { method: 'POST' });
    await loadSnapshot();
  }

  function updateRegion(field: keyof CaptureRegion, percent: number) {
    setDraftSettings((current) => {
      if (!current) return current;
      const value = percent / 100;
      const nextRegion = { ...current.region, [field]: value };
      if (field === 'left') nextRegion.width = Math.min(nextRegion.width, 1 - value);
      if (field === 'top') nextRegion.height = Math.min(nextRegion.height, 1 - value);
      if (field === 'width') nextRegion.width = Math.min(value, 1 - nextRegion.left);
      if (field === 'height') nextRegion.height = Math.min(value, 1 - nextRegion.top);
      return { ...current, region: nextRegion };
    });
  }

  async function saveSettings() {
    if (!draftSettings) return;
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/settings`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draftSettings),
      });
      if (!response.ok) throw new Error('Could not save capture settings');
      const saved = await response.json();
      setDraftSettings(saved);
      setStatus((current) => current ? { ...current, settings: saved } : current);
      setSettingsOpen(false);
    } finally {
      setSaving(false);
    }
  }

  async function refreshTextMaps() {
    setRefreshingMaps(true);
    await fetch(`${API_URL}/api/textmaps/update`, { method: 'POST' });
    await loadSnapshot();
  }

  const capture = status?.capture;
  const mapStatus = status?.textmaps;
  const currentCount = status?.session.line_count ?? sessionLines.length;
  const previewRegionQuery = draftSettings
    ? new URLSearchParams({
        left: String(draftSettings.region.left),
        top: String(draftSettings.region.top),
        width: String(draftSettings.region.width),
        height: String(draftSettings.region.height),
        t: String(previewTick),
      }).toString()
    : `t=${previewTick}`;

  return (
    <main className="companion-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Zenless Zone Zero</p>
          <h1>Proxy Transcript</h1>
        </div>
        <div className={`live-state ${online ? '' : 'is-offline'}`}>
          <span className="live-pulse" />
          <span>{online ? phaseLabel(capture?.phase ?? 'starting') : 'Service offline'}</span>
        </div>
      </header>

      <section className="status-strip" aria-label="Companion status">
        <div>
          <Radio size={17} />
          <span>English OCR</span>
          <strong>{capture?.running ? phaseLabel(capture.phase) : 'Paused'}</strong>
        </div>
        <div>
          <Database size={17} />
          <span>TextMaps</span>
          <strong>{mapStatus?.ready ? `${mapStatus.entry_count.toLocaleString()} pairs` : mapStatus?.message ?? 'Connecting'}</strong>
        </div>
        <div>
          <Activity size={17} />
          <span>This session</span>
          <strong>{currentCount} {currentCount === 1 ? 'line' : 'lines'}</strong>
        </div>
      </section>

      <section className={`current-line ${latestLine ? '' : 'is-empty'}`} aria-labelledby="current-heading">
        <div className="section-label">
          <span id="current-heading"><Crosshair size={16} /> Current line</span>
          {latestLine ? (
            <span className="match-label">
              {latestLine.match_kind === 'exact' ? 'Official match' : 'Fuzzy match'} · {Math.round(latestLine.score)}%
            </span>
          ) : null}
        </div>
        {latestLine ? (
          <div className="current-pair">
            <p className="current-english">{latestLine.english}</p>
            <p className="current-chinese" lang="zh-Hans">{latestLine.chinese}</p>
          </div>
        ) : (
          <div className="current-empty">
            <ScanLine size={28} />
            <div>
              <strong>{capture?.message ?? 'Connecting to the capture service'}</strong>
              <p>{capture?.last_ocr || 'The next matched subtitle will appear here automatically.'}</p>
            </div>
          </div>
        )}
      </section>

      <section className="transcript" aria-labelledby="transcript-heading">
        <div className="transcript-heading">
          <div>
            <p className="eyebrow">Persistent local history</p>
            <h2 id="transcript-heading">Transcript</h2>
          </div>
          <p>Newest first · English and Chinese stay paired</p>
        </div>

        <div className="column-labels" aria-hidden="true">
          <span>Time</span><span>English</span><span>中文</span><span>Match</span>
        </div>
        <div className="line-list">
          {lines.length ? lines.map((line) => (
            <article className="transcript-line" key={line.id}>
              <time dateTime={line.created_at}>{formatTime(line.created_at)}</time>
              <p>{line.english}</p>
              <p lang="zh-Hans">{line.chinese}</p>
              <span className={line.score < 90 ? 'is-low-score' : ''}>{Math.round(line.score)}%</span>
            </article>
          )) : (
            <div className="transcript-empty">
              <Database size={24} />
              <p>Your matched lines will accumulate here and remain after a restart.</p>
            </div>
          )}
        </div>
      </section>

      <footer className="capture-footer">
        <span className={capture?.phase === 'error' ? 'has-error' : ''}>
          <span className="live-pulse" /> {capture?.message ?? 'Connecting to local capture service'}
        </span>
        <div className="footer-actions">
          <Button variant="outline" onClick={toggleCapture} disabled={!online || !status}>
            {capture?.running ? <Pause /> : <Play />}
            {capture?.running ? 'Pause' : 'Start'}
          </Button>
          <Button onClick={() => setSettingsOpen(true)} disabled={!online || !draftSettings}>
            <Settings2 /> Capture setup
          </Button>
        </div>
      </footer>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="setup-dialog sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Capture setup</DialogTitle>
            <DialogDescription>
              Keep the subtitle region tight: include dialogue, but exclude dialogue choices and HUD text.
            </DialogDescription>
          </DialogHeader>

          <div className="capture-preview">
            {capture?.crop_bounds ? (
              <img
                key={previewTick}
                src={`${API_URL}/api/capture/preview.jpg?${previewRegionQuery}`}
                alt="Live preview of the game subtitle capture region"
              />
            ) : (
              <div className="preview-placeholder"><ScanLine /> Start ZZZ to see the capture preview.</div>
            )}
            <span>Live crop</span>
          </div>

          {draftSettings ? (
            <div className="region-controls">
              {([
                ['left', 'Left edge'],
                ['width', 'Width'],
                ['top', 'Top edge'],
                ['height', 'Height'],
              ] as const).map(([field, label]) => (
                <label key={field}>
                  <span>{label}<strong>{Math.round(draftSettings.region[field] * 100)}%</strong></span>
                  <input
                    type="range"
                    min={field === 'width' || field === 'height' ? 5 : 0}
                    max={100}
                    step={1}
                    value={Math.round(draftSettings.region[field] * 100)}
                    onChange={(event) => updateRegion(field, Number(event.target.value))}
                  />
                </label>
              ))}
            </div>
          ) : null}

          <div className="ocr-readout">
            <span>Latest OCR</span>
            <p>{capture?.last_ocr || 'No English text detected in the current region.'}</p>
            <small>{capture?.last_ocr_confidence ? `${Math.round(capture.last_ocr_confidence)}% OCR confidence` : 'Waiting for text'}</small>
          </div>

          <div className="setup-actions">
            <Button variant="outline" onClick={refreshTextMaps} disabled={refreshingMaps}>
              <RefreshCw className={refreshingMaps ? 'is-spinning' : ''} />
              {refreshingMaps ? 'Updating…' : 'Update TextMaps'}
            </Button>
            <Button onClick={saveSettings} disabled={!draftSettings || saving}>
              {saving ? 'Saving…' : 'Save capture region'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
