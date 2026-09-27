'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Crosshair,
  Database,
  MessageSquareText,
  Pause,
  Play,
  Radio,
  RefreshCw,
  ScanLine,
  Settings2,
  Star,
  Users,
  Volume2,
  Gamepad2,
  Send,
  Check,
  Loader2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ReadingText, type PinyinMode } from '@/app/reading-text';
import { createVoiceActivityFollower, type VoiceActivity } from '@/lib/voice-activity';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const API_URL = 'http://127.0.0.1:8766';
const WS_URL = 'ws://127.0.0.1:8766/api/ws';
const HISTORY_LIMIT = 50;
const HISTORY_PAGE_SIZE = 10;

type CaptureRegion = { left: number; top: number; width: number; height: number };
type Settings = {
  preferred_game: 'auto' | 'zzz' | 'pragmata';
  process_names: string[];
  window_title_contains: string[];
  region: CaptureRegion;
  tip_region: CaptureRegion;
  cinematic_region: CaptureRegion;
  scan_interval_ms: number;
  stable_frames: number;
  fuzzy_threshold: number;
  auto_start: boolean;
  save_unmatched: boolean;
};
type CaptureStatus = {
  visible_text_ids: string[];
  running: boolean;
  phase: string;
  message: string;
  active_game: 'zzz' | 'pragmata' | null;
  window_title: string | null;
  window_bounds: [number, number, number, number] | null;
  crop_bounds: [number, number, number, number] | null;
  tip_crop_bounds: [number, number, number, number] | null;
  cinematic_crop_bounds: [number, number, number, number] | null;
  last_ocr: string;
  last_ocr_confidence: number | null;
  last_tip_ocr: string;
  last_tip_ocr_confidence: number | null;
  last_tip_match_score: number | null;
  last_cinematic_ocr: string;
  last_cinematic_ocr_confidence: number | null;
  last_cinematic_match_score: number | null;
  last_match_score: number | null;
  last_scan_at: string | null;
  last_error: string | null;
};
type TextMapStatus = { ready: boolean; state: string; message: string; entry_count: number };
type TranscriptLine = {
  id: number;
  created_at: string;
  session_id: string;
  game: 'zzz' | 'pragmata';
  source_ocr: string;
  english: string;
  chinese: string;
  text_id: string;
  score: number;
  match_kind: string;
  ambiguous: boolean;
  channel: 'dialogue' | 'gameplay' | 'tip' | 'cinematic';
  voiced: boolean;
  has_audio: boolean;
  audio_pending?: boolean;
  audio_source?: 'original' | 'recording';
  speaker_english?: string | null;
  speaker_chinese?: string | null;
  favorite: boolean;
};
type UpdateStatus = {
  state: string;
  message: string;
  progress: number;
  automatic: boolean;
  last_checked: string | null;
  last_error: string | null;
};
type StatusPayload = {
  capture: CaptureStatus;
  textmaps: TextMapStatus;
  game_textmaps?: Record<'zzz' | 'pragmata', TextMapStatus>;
  audio: { ready: boolean; message: string };
  agents?: { indexed_clips: number; total_clips: number; selected_agent: string | null; last_error: string | null; saved_lines: number; update?: { state: string; message: string; automatic: boolean } };
  voice_activity?: VoiceActivity | null;
  updates?: UpdateStatus;
  settings: Settings;
  session: { id: string; line_count: number; total_line_count: number };
};
type TranscriptTab = 'history' | 'agents' | 'favorites';
type GameId = 'zzz' | 'pragmata';
type AgentLine = { key: string; agent: string; asset_id: string; chinese: string; text_source: string; last_heard: string; heard_count: number };
type AgentPage = { lines: AgentLine[]; total: number };
type LexiriseStatus = { configured: boolean; sent: Record<string, number> };
type ReadingMode = 'migaku' | 'lexirise';

const LexiriseButton = memo(function LexiriseButton({ sent, busy, disabled, game, onClick, compact = false }: {
  sent: boolean; busy: boolean; disabled: boolean; game: GameId; onClick: () => void; compact?: boolean;
}) {
  const title = sent ? 'Already sent to Lexirise' : `Send sentence and voice to Lexirise · ${game === 'zzz' ? 'Zenless Zone Zero' : 'PRAGMATA'}`;
  return <button type="button" className={`lexirise-send ${sent ? 'is-sent' : ''}`} translate="no"
    disabled={disabled || busy || sent} onClick={onClick} title={title} aria-label={title} aria-busy={busy}>
    {busy ? <Loader2 size={16} className="animate-spin" /> : sent ? <Check size={16} /> : <Send size={16} />}
    {!compact && <span>{busy ? 'Sending…' : sent ? 'Sent to Lexirise' : 'Lexirise'}</span>}
  </button>;
});

function mergeAgentLines(current: AgentLine[], incoming: AgentLine[]) {
  const entries = new Map(current.map(line => [line.key, line]));
  for (const line of incoming) {
    if (!entries.has(line.key) || entries.get(line.key)!.last_heard <= line.last_heard) entries.set(line.key, line);
  }
  return [...entries.values()].sort((a,b) => b.last_heard.localeCompare(a.last_heard) || b.key.localeCompare(a.key));
}

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

function formatTime(value: string) {
  return timeFormatter.format(new Date(value));
}

function sameStringArray(left: string[], right: string[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function sameBounds(
  left: [number, number, number, number] | null,
  right: [number, number, number, number] | null,
) {
  if (left === right) return true;
  return !!left && !!right && left.every((value, index) => value === right[index]);
}

function captureStatusEqual(left: CaptureStatus, right: CaptureStatus, includeDiagnostics: boolean) {
  const visibleStateMatches = left.running === right.running
    && left.phase === right.phase
    && left.message === right.message
    && left.active_game === right.active_game
    && left.last_error === right.last_error
    && sameStringArray(left.visible_text_ids, right.visible_text_ids);
  if (!visibleStateMatches || !includeDiagnostics) return visibleStateMatches;

  return left.window_title === right.window_title
    && sameBounds(left.window_bounds, right.window_bounds)
    && sameBounds(left.crop_bounds, right.crop_bounds)
    && sameBounds(left.tip_crop_bounds, right.tip_crop_bounds)
    && sameBounds(left.cinematic_crop_bounds, right.cinematic_crop_bounds)
    && left.last_ocr === right.last_ocr
    && left.last_ocr_confidence === right.last_ocr_confidence
    && left.last_tip_ocr === right.last_tip_ocr
    && left.last_tip_ocr_confidence === right.last_tip_ocr_confidence
    && left.last_tip_match_score === right.last_tip_match_score
    && left.last_cinematic_ocr === right.last_cinematic_ocr
    && left.last_cinematic_ocr_confidence === right.last_cinematic_ocr_confidence
    && left.last_cinematic_match_score === right.last_cinematic_match_score
    && left.last_match_score === right.last_match_score;
}

function transcriptLineEqual(left: TranscriptLine, right: TranscriptLine) {
  const leftEntries = Object.entries(left);
  const rightEntries = Object.entries(right);
  return leftEntries.length === rightEntries.length
    && leftEntries.every(([key, value]) => Object.is(value, right[key as keyof TranscriptLine]));
}

function mergeTranscriptSnapshot(current: TranscriptLine[], snapshot: TranscriptLine[]) {
  const currentById = new Map(current.map((line) => [line.id, line]));
  const snapshotIds = new Set(snapshot.map((line) => line.id));
  const newestSnapshotId: Partial<Record<GameId, number>> = {};
  for (const line of snapshot) {
    newestSnapshotId[line.game] = Math.max(newestSnapshotId[line.game] ?? 0, line.id);
  }

  const merged = snapshot.map((line) => {
    const existing = currentById.get(line.id);
    return existing && transcriptLineEqual(existing, line) ? existing : line;
  });
  for (const line of current) {
    if (snapshotIds.has(line.id)) continue;
    // WebSocket lines can arrive before their audio is ready and therefore
    // before /api/lines returns them. Keep those lines through background sync.
    if (line.audio_pending || line.id > (newestSnapshotId[line.game] ?? 0)) merged.push(line);
  }
  return merged.sort((left, right) => right.id - left.id);
}

function phaseLabel(phase: string) {
  const labels: Record<string, string> = {
    starting: 'Starting',
    waiting_for_game: 'Waiting for game',
    loading_textmaps: 'Loading TextMaps',
    listening: 'Listening',
    unmatched: 'Reading subtitle',
    excluded_screen: 'History UI ignored',
    matched: 'Matched',
    agents: 'Agent voices',
    error: 'Retrying',
    stopped: 'Paused',
  };
  return labels[phase] ?? phase.replaceAll('_', ' ');
}

export function Companion() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <main className="companion-shell" aria-busy="true" />;
  return <CompanionClient />;
}

const StableText = memo(function StableText({ text, className, lang }: { text: string; className?: string; lang?: string }) {
  const element = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (element.current && element.current.textContent !== text) {
      // Migaku rewrites target-language text into its own spans. React must not
      // reconcile those injected children or it can crash on the next update.
      element.current.replaceChildren(document.createTextNode(text));
    }
  }, [text]);
  return <p ref={element} className={className} lang={lang} />;
});

const StableInline = memo(function StableInline({ text, className }: { text: string; className?: string }) {
  const element = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (element.current && element.current.textContent !== text) {
      element.current.replaceChildren(document.createTextNode(text));
    }
  }, [text]);
  return <span ref={element} className={className} />;
});

const MigakuCurrentText = memo(function MigakuCurrentText({ text, lineId }: { text: string; lineId: number }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const paragraph = document.createElement('p');
    paragraph.className = 'current-chinese';
    paragraph.lang = 'zh-Hans';
    paragraph.dataset.migakuLineId = String(lineId);
    paragraph.textContent = text;
    // A fresh node is important: Migaku processes newly inserted transcript
    // nodes, but does not reliably revisit text replaced inside an old node.
    host.current.replaceChildren(paragraph);
  }, [lineId, text]);
  return <div className="current-chinese-host" ref={host} />;
});

const TranscriptRow = memo(function TranscriptRow({
  line,
  readingMode,
  pinyinMode,
  canUseLexirise,
  sendingRef,
  sentToLexirise,
  onPlay,
  onToggleFavorite,
  onSendToLexirise,
}: {
  line: TranscriptLine;
  readingMode: ReadingMode;
  pinyinMode: PinyinMode;
  canUseLexirise: boolean;
  sendingRef: string | null;
  sentToLexirise: boolean;
  onPlay: (line: TranscriptLine) => void;
  onToggleFavorite: (line: TranscriptLine) => void;
  onSendToLexirise: (kind: 'line' | 'agent', id: number | string) => void;
}) {
  const ref = `line:${line.id}`;
  return <article className="transcript-line">
    <div className="line-time">
      <time dateTime={line.created_at}>{formatTime(line.created_at)}</time>
      <small className={line.channel !== 'dialogue' ? 'is-tip' : ''}>{line.channel === 'tip' ? 'TOP-RIGHT' : line.channel === 'cinematic' ? 'CINEMATIC' : line.channel === 'gameplay' ? 'GAMEPLAY' : 'DIALOGUE'}</small>
    </div>
    <div className="line-language">
      {line.speaker_english && <StableInline className="line-speaker" text={line.speaker_english} />}
      <StableText text={line.english} />
    </div>
    <div className="line-language">
      {line.speaker_chinese && <StableInline className="line-speaker speaker-chinese" text={line.speaker_chinese} />}
      {readingMode === 'lexirise' ? <ReadingText id={line.id} text={line.chinese} pinyin={pinyinMode} /> : <StableText lang="zh-Hans" text={line.chinese} />}
    </div>
    <div className="line-meta">
      <span className={line.score < 90 ? 'is-low-score' : ''}>{Math.round(line.score)}%</span>
      <div className="line-actions">
        <button type="button" onClick={() => onPlay(line)} disabled={!line.has_audio} aria-label={`Play voice line: ${line.english}`} title="Play voice line"><Volume2 size={16} /></button>
        <button type="button" className={line.favorite ? 'is-favorite' : ''} onClick={() => onToggleFavorite(line)} aria-label={line.favorite ? 'Remove from favorites' : 'Favorite line'} title={line.favorite ? 'Remove favorite' : 'Keep forever'}><Star size={16} fill={line.favorite ? 'currentColor' : 'none'} /></button>
        <LexiriseButton
          sent={sentToLexirise}
          busy={sendingRef === ref}
          disabled={!canUseLexirise || !line.has_audio || (sendingRef !== null && sendingRef !== ref)}
          game={line.game}
          onClick={() => onSendToLexirise('line', line.id)}
          compact
        />
      </div>
    </div>
  </article>;
});

function CompanionClient() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [online, setOnline] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsOpenRef = useRef(false);
  const [draftSettings, setDraftSettings] = useState<Settings | null>(null);
  const [previewTick, setPreviewTick] = useState(0);
  const [setupChannel, setSetupChannel] = useState<'dialogue' | 'tip' | 'cinematic'>('dialogue');
  const [saving, setSaving] = useState(false);
  const [refreshingMaps, setRefreshingMaps] = useState(false);
  const [snapshotLoaded, setSnapshotLoaded] = useState(false);
  const [transcriptTab, setTranscriptTab] = useState<TranscriptTab>('history');
  const transcriptTabRef = useRef<TranscriptTab>('history');
  const [historyPage, setHistoryPage] = useState(0);
  const changeTranscriptTab = useCallback((tab: TranscriptTab, resetHistory = false) => {
    if (resetHistory || transcriptTabRef.current !== tab) setHistoryPage(0);
    transcriptTabRef.current = tab;
    setTranscriptTab(tab);
  }, []);
  const [selectedGame, setSelectedGame] = useState<GameId>('zzz');
  const lastActiveGame = useRef<GameId | null>(null);
  const followVoice = useRef(createVoiceActivityFollower(changeTranscriptTab));
  const [agentLines, setAgentLines] = useState<AgentLine[]>([]);
  const [agentTotal, setAgentTotal] = useState(0);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const knownLineIds = useRef(new Set<number>());
  const historyList = useRef<HTMLDivElement>(null);
  const playback = useRef<HTMLAudioElement | null>(null);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [lexirise, setLexirise] = useState<LexiriseStatus>({ configured: false, sent: {} });
  const [readingMode, setReadingMode] = useState<ReadingMode>('migaku');
  const [pinyinMode, setPinyinMode] = useState<PinyinMode>('unknown');
  const [sendingRef, setSendingRef] = useState<string | null>(null);
  const [studyMessage, setStudyMessage] = useState('');
  const sendingStudy = useRef(false);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem('proxy-transcript-playback-rate'));
    if ([1, 0.85, 0.75, 0.6].includes(saved)) setPlaybackRate(saved);
    const reader = window.localStorage.getItem('proxy-transcript-reading-mode');
    if (reader === 'migaku' || reader === 'lexirise') setReadingMode(reader);
    const pinyin = window.localStorage.getItem('proxy-transcript-pinyin-mode');
    if (pinyin === 'unknown' || pinyin === 'all' || pinyin === 'off') setPinyinMode(pinyin);
  }, []);

  useEffect(() => {
    settingsOpenRef.current = settingsOpen;
  }, [settingsOpen]);

  const loadSnapshot = useCallback(async () => {
    try {
      const [statusResponse, zzzLinesResponse, pragmataLinesResponse, zzzFavoritesResponse, pragmataFavoritesResponse, agentsResponse] = await Promise.all([
        fetch(`${API_URL}/api/status`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/lines?limit=50&game=zzz`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/lines?limit=50&game=pragmata`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/favorites?game=zzz`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/favorites?game=pragmata`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/agents`, { cache: 'no-store' }),
      ]);
      if (!statusResponse.ok || !zzzLinesResponse.ok || !pragmataLinesResponse.ok || !zzzFavoritesResponse.ok || !pragmataFavoritesResponse.ok) {
        throw new Error('Companion service unavailable');
      }
      const nextStatus = (await statusResponse.json()) as StatusPayload;
      setStatus(nextStatus);
      followVoice.current(nextStatus.voice_activity);
      setDraftSettings(nextStatus.settings);
      const recentLines = [
        ...(await zzzLinesResponse.json()) as TranscriptLine[],
        ...(await pragmataLinesResponse.json()) as TranscriptLine[],
      ];
      const favoriteLines = [
        ...(await zzzFavoritesResponse.json()) as TranscriptLine[],
        ...(await pragmataFavoritesResponse.json()) as TranscriptLine[],
      ];
      const nextLines = Array.from(
        new Map([...recentLines, ...favoriteLines].map((line) => [line.id, line])).values(),
      ).sort((left, right) => right.id - left.id);
      setLines((current) => {
        const merged = mergeTranscriptSnapshot(current, nextLines);
        knownLineIds.current = new Set(merged.map((line) => line.id));
        return merged;
      });
      if (agentsResponse.ok) {
        const agents = (await agentsResponse.json()) as AgentPage;
        setAgentLines(current => mergeAgentLines(current, agents.lines));
        setAgentTotal(agents.total);
      }
      setOnline(true);
      setSnapshotLoaded(true);
      // Integration status must not prevent the transcript from loading.
      void fetch(`${API_URL}/api/lexirise`, { cache: 'no-store' })
        .then(response => response.ok ? response.json() : null)
        .then(value => { if (value) setLexirise(value as LexiriseStatus); }).catch(() => undefined);
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    void loadSnapshot();
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
          followVoice.current(event.snapshot.voice_activity);
          setDraftSettings(event.snapshot.settings);
        }
        if (event.type === 'capture_status') {
          const nextCapture = event.capture as CaptureStatus;
          setStatus((current) => current && !captureStatusEqual(current.capture, nextCapture, settingsOpenRef.current)
            ? { ...current, capture: nextCapture }
            : current);
        }
        if (event.type === 'textmaps_status') {
          setRefreshingMaps(false);
          setStatus((current) => current ? { ...current, textmaps: event.textmaps } : current);
        }
        if (event.type === 'update_status') {
          setStatus((current) => current ? { ...current, updates: event.updates } : current);
        }
        if (event.type === 'settings') {
          setDraftSettings(event.settings);
          setStatus((current) => current ? { ...current, settings: event.settings } : current);
        }
        if (event.type === 'line') {
          const line = event.line as TranscriptLine;
          if (!line.voiced) return;
          const isNew = !knownLineIds.current.has(line.id);
          knownLineIds.current.add(line.id);
          setLines((current) => {
            const existing = current.some((item) => item.id === line.id);
            return (existing
              ? current.map((item) => item.id === line.id ? line : item)
              : [line, ...current]
            ).sort((left, right) => right.id - left.id);
          });
          setStatus((current) => current ? {
            ...current,
            session: {
              ...current.session,
              line_count: current.session.line_count + (isNew ? 1 : 0),
              total_line_count: current.session.total_line_count + (isNew ? 1 : 0),
            },
          } : current);
        }
        if (event.type === 'agent_line') {
          setAgentLines(current => mergeAgentLines(current, [event.line as AgentLine]));
        }
        if (event.type === 'voice_activity') {
          followVoice.current(event.activity);
        }
        if (event.type === 'line_deleted') {
          const lineId = Number(event.line_id);
          const existed = knownLineIds.current.delete(lineId);
          setLines((current) => current.filter((item) => item.id !== lineId));
          if (existed) {
            setStatus((current) => current ? {
              ...current,
              session: {
                ...current.session,
                line_count: Math.max(0, current.session.line_count - 1),
                total_line_count: Math.max(0, current.session.total_line_count - 1),
              },
            } : current);
          }
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

  useEffect(() => {
    const active = status?.capture.active_game;
    if (active && active !== lastActiveGame.current) {
      lastActiveGame.current = active;
      setSelectedGame(active);
      setHistoryPage(0);
      if (active === 'pragmata' && transcriptTab === 'agents') changeTranscriptTab('history');
    }
  }, [changeTranscriptTab, status?.capture.active_game, transcriptTab]);

  const recentLines = useMemo(
    () => lines.filter((line) => line.game === selectedGame).slice(0, HISTORY_LIMIT),
    [lines, selectedGame],
  );
  const visibleLine = recentLines.find((line) =>
    line.session_id === status?.session.id
    && line.voiced
    && status?.capture.running
    && status.capture.visible_text_ids?.includes(line.text_id)
  ) ?? null;
  const latestSessionLine = recentLines.find((line) =>
    line.session_id === status?.session.id && line.voiced
  ) ?? null;
  // Free-roam subtitles disappear from the game almost immediately. Keep the
  // newest one available to read/Migaku until any later voiced line arrives.
  // Other presentation modes still disappear from Current line with the game.
  const latestLine = visibleLine ?? (
    latestSessionLine && (latestSessionLine.channel === 'gameplay' || latestSessionLine.game === 'pragmata')
      ? latestSessionLine
      : null
  );
  const historyLines = useMemo(
    () => recentLines.filter((line) => line.id !== latestLine?.id),
    [recentLines, latestLine?.id],
  );
  const favoriteLines = useMemo(
    () => lines.filter((line) => line.game === selectedGame && line.favorite),
    [lines, selectedGame],
  );
  const historyPageCount = Math.max(1, Math.ceil(historyLines.length / HISTORY_PAGE_SIZE));
  const currentHistoryPage = Math.min(historyPage, historyPageCount - 1);
  const visibleTranscriptLines = transcriptTab === 'favorites'
    ? favoriteLines
    : historyLines.slice(
        currentHistoryPage * HISTORY_PAGE_SIZE,
        (currentHistoryPage + 1) * HISTORY_PAGE_SIZE,
      );
  const sessionId = status?.session.id;
  const sessionLines = useMemo(
    () => lines.filter((line) => line.game === selectedGame && (!sessionId || line.session_id === sessionId)),
    [lines, selectedGame, sessionId],
  );
  useEffect(() => {
    if (historyList.current) historyList.current.scrollTop = 0;
  }, [historyLines.length, favoriteLines.length, transcriptTab, currentHistoryPage]);

  async function toggleCapture() {
    if (!status) return;
    const action = status.capture.running ? 'stop' : 'start';
    await fetch(`${API_URL}/api/capture/${action}`, { method: 'POST' });
    await loadSnapshot();
  }

  function updateRegion(field: keyof CaptureRegion, percent: number) {
    setDraftSettings((current) => {
      if (!current) return current;
      const regionKey = setupChannel === 'tip'
        ? 'tip_region'
        : setupChannel === 'cinematic' ? 'cinematic_region' : 'region';
      const value = percent / 100;
      const nextRegion = { ...current[regionKey], [field]: value };
      if (field === 'left') nextRegion.width = Math.min(nextRegion.width, 1 - value);
      if (field === 'top') nextRegion.height = Math.min(nextRegion.height, 1 - value);
      if (field === 'width') nextRegion.width = Math.min(value, 1 - nextRegion.left);
      if (field === 'height') nextRegion.height = Math.min(value, 1 - nextRegion.top);
      return { ...current, [regionKey]: nextRegion };
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
      const saved = (await response.json()) as Settings;
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

  const toggleFavorite = useCallback(async (line: TranscriptLine) => {
    const favorite = !line.favorite;
    setLines((current) => current.map((item) => item.id === line.id ? { ...item, favorite } : item));
    const response = await fetch(`${API_URL}/api/lines/${line.id}/favorite`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ favorite }),
    });
    if (!response.ok) await loadSnapshot();
  }, [loadSnapshot]);

  const playLine = useCallback((line: TranscriptLine) => {
    if (!line.has_audio) return;
    playback.current?.pause();
    const audio = new Audio(`${API_URL}/api/lines/${line.id}/audio?v=${line.id}-${line.audio_source ?? 'recording'}`);
    audio.playbackRate = playbackRate;
    playback.current = audio;
    void audio.play();
  }, [playbackRate]);

  const sendToLexirise = useCallback(async (kind: 'line' | 'agent', id: number | string) => {
    if (sendingStudy.current) return;
    sendingStudy.current = true;
    const ref = `${kind}:${id}`;
    setSendingRef(ref);
    setStudyMessage('Sending sentence and voice to Lexirise…');
    try {
      const response = await fetch(`${API_URL}/api/${kind === 'line' ? 'lines' : 'agents'}/${id}/lexirise`, {
        method: 'POST', headers: { 'X-Proxy-Transcript': 'lexirise' },
      });
      const result = await response.json() as { detail?: string; deck_id: number; already_sent?: boolean };
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not send to Lexirise.');
      setLexirise(current => ({ ...current, sent: { ...current.sent, [ref]: result.deck_id } }));
      setStudyMessage(`${result.already_sent ? 'Already saved' : 'Sentence and voice saved'} in Lexirise · ${result.deck_id === 1951 ? 'PRAGMATA' : 'Zenless Zone Zero'}.`);
    } catch (error) {
      setStudyMessage(error instanceof Error ? error.message : 'Could not reach Lexirise. Please retry.');
    } finally {
      sendingStudy.current = false;
      setSendingRef(null);
    }
  }, []);

  function studyButton(kind: 'line' | 'agent', id: number | string, game: GameId, hasAudio: boolean, compact = false) {
    const ref = `${kind}:${id}`;
    return <LexiriseButton sent={!!lexirise.sent[ref]} busy={sendingRef === ref}
      disabled={!online || !lexirise.configured || !hasAudio || (sendingRef !== null && sendingRef !== ref)}
      game={game} onClick={() => void sendToLexirise(kind, id)} compact={compact} />;
  }

  function playAgent(line: AgentLine) {
    playback.current?.pause();
    const audio = new Audio(`${API_URL}/api/agents/${line.asset_id}/audio`);
    audio.playbackRate = playbackRate;
    playback.current = audio;
    void audio.play().catch(() => undefined);
  }

  function changePlaybackRate(value: number) {
    setPlaybackRate(value);
    window.localStorage.setItem('proxy-transcript-playback-rate', String(value));
    if (playback.current) playback.current.playbackRate = value;
  }

  async function loadMoreAgents() {
    setLoadingAgents(true);
    try {
      const response = await fetch(`${API_URL}/api/agents?offset=${agentLines.length}&limit=100`, { cache: 'no-store' });
      if (response.ok) {
        const page = (await response.json()) as AgentPage;
        setAgentLines(current => mergeAgentLines(current, page.lines));
        setAgentTotal(page.total);
      }
    } finally { setLoadingAgents(false); }
  }

  const capture = status?.capture;
  const mapStatus = status?.textmaps;
  const updateStatus = status?.updates;
  const currentCount = sessionLines.length;
  const activeRegion = draftSettings
    ? (setupChannel === 'tip'
        ? draftSettings.tip_region
        : setupChannel === 'cinematic' ? draftSettings.cinematic_region : draftSettings.region)
    : null;
  const previewRegionQuery = draftSettings
    ? new URLSearchParams({
        left: String(activeRegion?.left),
        top: String(activeRegion?.top),
        width: String(activeRegion?.width),
        height: String(activeRegion?.height),
        t: String(previewTick),
      }).toString()
    : `t=${previewTick}`;

  // The first visible render already has the correct controls and transcript
  // structure. This avoids a large reconciliation while Migaku parses the page.
  if (!snapshotLoaded) return <main className="companion-shell" aria-busy="true" />;

  return (
    <main className="companion-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">{selectedGame === 'pragmata' ? 'PRAGMATA' : 'Zenless Zone Zero'}</p>
          <h1>Proxy Transcript</h1>
        </div>
        <div className={`live-state ${online ? '' : 'is-offline'}`}>
          <span className="live-pulse" />
          <StableInline text={online ? phaseLabel(capture?.phase ?? 'starting') : 'Service offline'} />
        </div>
      </header>

      <nav className="game-tabs" aria-label="Game transcript">
        <span><Gamepad2 size={15} /> Game</span>
        <button type="button" className={selectedGame === 'zzz' ? 'is-active' : ''} aria-pressed={selectedGame === 'zzz'} onClick={() => { setSelectedGame('zzz'); setHistoryPage(0); }}>
          Zenless Zone Zero
        </button>
        <button type="button" className={selectedGame === 'pragmata' ? 'is-active' : ''} aria-pressed={selectedGame === 'pragmata'} onClick={() => { setSelectedGame('pragmata'); setHistoryPage(0); if (transcriptTab === 'agents') changeTranscriptTab('history'); }}>
          PRAGMATA
        </button>
        {status?.capture.active_game && <small>Capturing {status.capture.active_game === 'pragmata' ? 'PRAGMATA' : 'Zenless Zone Zero'}</small>}
        <div className="reading-controls" aria-label="Chinese reading options">
        <label>Reading <select value={readingMode} onChange={event => {
          const value = event.target.value as ReadingMode;
          setReadingMode(value); window.localStorage.setItem('proxy-transcript-reading-mode', value);
        }}><option value="migaku">Migaku</option><option value="lexirise" disabled={!lexirise.configured}>Lexirise</option></select></label>
        {readingMode === 'lexirise' && <label>Pinyin <select value={pinyinMode} onChange={event => {
          const value = event.target.value as PinyinMode;
          setPinyinMode(value); window.localStorage.setItem('proxy-transcript-pinyin-mode', value);
        }}><option value="unknown">Unknown words</option><option value="all">All words</option><option value="off">Off</option></select></label>}
        </div>
      </nav>

      <section className="status-strip" aria-label="Companion status">
        <div>
          <Radio size={17} />
          <span>{selectedGame === 'pragmata' ? 'Subtitle OCR + voice' : '3-zone OCR + voice'}</span>
          <strong><StableInline text={capture?.running ? phaseLabel(capture.phase) : 'Paused'} /></strong>
        </div>
        <div>
          <Database size={17} />
          <span>{selectedGame === 'pragmata' ? 'Official game text' : 'TextMaps'}</span>
          <strong><StableInline text={(status?.game_textmaps?.[selectedGame] ?? mapStatus)?.ready ? `${(status?.game_textmaps?.[selectedGame] ?? mapStatus)!.entry_count.toLocaleString()} pairs` : (status?.game_textmaps?.[selectedGame] ?? mapStatus)?.message ?? 'Connecting'} /></strong>
        </div>
        <div>
          <Activity size={17} />
          <span>This session</span>
          <strong><StableInline text={`${currentCount} ${currentCount === 1 ? 'line' : 'lines'}`} /></strong>
        </div>
      </section>

      {updateStatus && <section className={`update-progress is-${updateStatus.state}`} aria-label="Automatic data update status">
        <div className="update-progress-copy">
          <RefreshCw size={16} className={updateStatus.state === 'checking' || updateStatus.state === 'updating' ? 'is-spinning' : ''} />
          <strong>Automatic updates</strong>
          <StableInline text={updateStatus.message} />
        </div>
        <Progress value={updateStatus.progress} aria-label={`${updateStatus.progress}% complete`} />
        <span className="update-progress-value">{updateStatus.progress}%</span>
      </section>}

      {transcriptTab !== 'agents' && <section className={`current-line game-${selectedGame} ${latestLine ? '' : 'is-empty'}`} aria-labelledby="current-heading">
        <div className="section-label">
          <span id="current-heading"><Crosshair size={16} /> Current line</span>
          {latestLine ? (
            <StableInline
              className="match-label"
              text={`${latestLine.game === 'pragmata' ? 'PRAGMATA dialogue' : latestLine.channel === 'tip' ? 'Top-right voice' : latestLine.channel === 'cinematic' ? 'Cinematic / comic' : latestLine.channel === 'gameplay' ? 'Gameplay voice' : 'Dialogue'} · ${latestLine.voiced ? 'Voiced' : 'Checking voice…'} · ${Math.round(latestLine.score)}%`}
            />
          ) : null}
        </div>
        {latestLine ? (
          <div className="current-pair">
            {(latestLine.speaker_english || latestLine.speaker_chinese) && <div className="current-speaker">
              {latestLine.speaker_english && <StableInline text={latestLine.speaker_english} />}
              {latestLine.speaker_chinese && <StableInline className="speaker-chinese" text={latestLine.speaker_chinese} />}
            </div>}
            <StableText className="current-english" text={latestLine.english} />
            {readingMode === 'lexirise' ? <ReadingText id={latestLine.id} text={latestLine.chinese} pinyin={pinyinMode} current /> : <MigakuCurrentText text={latestLine.chinese} lineId={latestLine.id} />}
            <div className="current-actions">
              <button type="button" onClick={() => playLine(latestLine)} disabled={!latestLine.has_audio} aria-label={latestLine.has_audio ? 'Play current voice line' : latestLine.audio_pending ? 'Preparing original voice' : 'Voice audio was missed'} title={latestLine.has_audio ? 'Play voice line' : latestLine.audio_pending ? 'Preparing original game audio' : 'Text captured; voice audio was missed'}>
                <Volume2 size={18} /> {latestLine.audio_pending ? 'Preparing voice…' : !latestLine.has_audio ? 'Voice missed' : latestLine.audio_source === 'original' ? 'Original voice' : 'Play voice'}
              </button>
              <button type="button" className={latestLine.favorite ? 'is-favorite' : ''} onClick={() => toggleFavorite(latestLine)} aria-label={latestLine.favorite ? 'Remove current line from favorites' : 'Favorite current line'} title={latestLine.favorite ? 'Remove favorite' : 'Keep forever'}>
                <Star size={18} fill={latestLine.favorite ? 'currentColor' : 'none'} /> {latestLine.favorite ? 'Saved' : 'Favorite'}
              </button>
              {studyButton('line', latestLine.id, latestLine.game, latestLine.has_audio)}
            </div>
          </div>
        ) : (
          <div className="current-empty">
            <ScanLine size={28} />
            <div>
              <strong>No confirmed voiced subtitle on screen</strong>
              <p>The next voiced line will appear here. Previous lines stay in History.</p>
            </div>
          </div>
        )}
      </section>}

      <div className="study-status" role="status" aria-live="polite">
        {studyMessage || (online && !lexirise.configured ? 'Lexirise is not configured on this computer.' : '')}
      </div>
      <section className="transcript" aria-labelledby="transcript-heading">
        <div className="transcript-heading">
          <div>
            <p className="eyebrow">Saved transcript</p>
            <h2 id="transcript-heading">{transcriptTab === 'agents' ? 'Agent voices' : transcriptTab === 'favorites' ? 'Favorites' : 'Earlier lines'}</h2>
          </div>
          <p>{transcriptTab === 'agents' ? 'Last heard first · Kept between sessions' : transcriptTab === 'favorites' ? `${favoriteLines.length} saved forever` : '10 at a time · up to 50 recent lines'}</p>
        </div>

        <div className="transcript-tabs" role="tablist" aria-label="Transcript view">
          <button
            type="button"
            role="tab"
            aria-selected={transcriptTab === 'history'}
            className={transcriptTab === 'history' ? 'is-active' : ''}
            onClick={() => changeTranscriptTab('history', true)}
          >
            History
          </button>
          {selectedGame === 'zzz' && <button type="button" role="tab" aria-selected={transcriptTab === 'agents'}
            className={transcriptTab === 'agents' ? 'is-active' : ''} onClick={() => changeTranscriptTab('agents', true)}>
            <Users size={14} /> Agents <span>{Math.max(agentTotal,agentLines.length)}</span>
          </button>}
          <button
            type="button"
            role="tab"
            aria-selected={transcriptTab === 'favorites'}
            className={transcriptTab === 'favorites' ? 'is-active' : ''}
            onClick={() => changeTranscriptTab('favorites', true)}
          >
            <Star size={14} fill={transcriptTab === 'favorites' ? 'currentColor' : 'none'} />
            Favorites <span>{favoriteLines.length}</span>
          </button>
        </div>

        {transcriptTab === 'agents' ? <div className="agent-library">
          {status?.agents?.update && <p className="agent-note" role="status">{status.agents.update.message}</p>}
          <div className="agent-listening" role="status">
            <Radio size={16} />
            <span>{capture?.phase === 'agents'
              ? `Listening${status?.agents?.selected_agent ? ` to ${status.agents.selected_agent}` : ' for agent voices'}`
              : 'Open an agent in the game to recognize their voice lines.'}</span>
          </div>
          {status?.agents && status.agents.indexed_clips < status.agents.total_clips &&
            <p className="agent-note">Preparing audio recognition: {status.agents.indexed_clips.toLocaleString()} / {status.agents.total_clips.toLocaleString()} clips. Unindexed clips cannot be recognized yet.</p>}
          <p className="agent-note">Hanzi is transcribed from the matched original clip and may contain errors. Replays move the same entry to the top.</p>
          {status?.agents?.last_error && <p className="agent-note">Recognition issue: {status.agents.last_error}</p>}
          <div className="line-list agent-lines">
            {agentLines.map(line => <article className="agent-line" key={line.key}>
              <div className="agent-line-header"><strong>{line.agent}</strong><time dateTime={line.last_heard}>{formatTime(line.last_heard)}</time></div>
              <StableText lang="zh-Hans" text={line.chinese} />
              <div className="agent-line-footer">
                <span>Automatic transcription · Heard {line.heard_count} {line.heard_count === 1 ? 'time' : 'times'}</span>
                <Button variant="outline" size="sm" onClick={() => playAgent(line)} aria-label={`Play ${line.agent} voice line`}><Volume2 size={16} /> Play voice</Button>
                {studyButton('agent', line.asset_id, 'zzz', !!line.chinese)}
              </div>
            </article>)}
            {!agentLines.length && <div className="transcript-empty"><Users size={26} /><p>No agent voices heard yet. Play a line on an agent’s game screen; it will be saved here once recognized.</p></div>}
            {agentLines.length < agentTotal && <Button variant="outline" onClick={loadMoreAgents} disabled={loadingAgents}>{loadingAgents ? 'Loading…' : 'Load older voices'}</Button>}
          </div>
        </div> : <>
        <div className="column-labels" aria-hidden="true">
          <span>Time / type</span><span>English</span><span>中文</span><span>Match</span>
        </div>
        <div className="line-list" ref={historyList}>
          {visibleTranscriptLines.length ? visibleTranscriptLines.map((line) => (
            <TranscriptRow
              key={line.id}
              line={line}
              readingMode={readingMode}
              pinyinMode={pinyinMode}
              canUseLexirise={online && lexirise.configured}
              sendingRef={sendingRef}
              sentToLexirise={!!lexirise.sent[`line:${line.id}`]}
              onPlay={playLine}
              onToggleFavorite={toggleFavorite}
              onSendToLexirise={sendToLexirise}
            />
          )) : (
            <div className="transcript-empty">
              {transcriptTab === 'favorites' ? <Star size={24} /> : <Database size={24} />}
              <p>{transcriptTab === 'favorites'
                ? 'Favorite a line with the star button and it will stay here between sessions.'
                : `Your matched ${selectedGame === 'pragmata' ? 'PRAGMATA' : 'Zenless Zone Zero'} lines will remain after a restart.`}</p>
            </div>
          )}
        </div>
        {transcriptTab === 'history' && historyLines.length > HISTORY_PAGE_SIZE && (
          <nav className="history-pagination" aria-label="Transcript history pages">
            <button
              type="button"
              onClick={() => setHistoryPage(Math.max(0, currentHistoryPage - 1))}
              disabled={currentHistoryPage === 0}
            >
              Newer 10
            </button>
            <span>
              {currentHistoryPage * HISTORY_PAGE_SIZE + 1}–{Math.min((currentHistoryPage + 1) * HISTORY_PAGE_SIZE, historyLines.length)} of {historyLines.length}
            </span>
            <button
              type="button"
              onClick={() => setHistoryPage(Math.min(historyPageCount - 1, currentHistoryPage + 1))}
              disabled={currentHistoryPage >= historyPageCount - 1}
            >
              Previous 10
            </button>
          </nav>
        )}
        </>}
      </section>

      <footer className="capture-footer">
        <span className={capture?.phase === 'error' ? 'has-error' : ''}>
          <span className="live-pulse" /> <StableInline text={capture?.message ?? 'Connecting to local capture service'} />
        </span>
        <div className="footer-actions">
          <label className="playback-speed">
            <Volume2 size={16} />
            <span>Speed</span>
            <select value={playbackRate} onChange={(event) => changePlaybackRate(Number(event.target.value))} aria-label="Voice playback speed">
              <option value={1}>1×</option>
              <option value={0.85}>0.85×</option>
              <option value={0.75}>0.75×</option>
              <option value={0.6}>0.6×</option>
            </select>
          </label>
          <Button
            variant="outline"
            className={capture?.running ? 'capture-toggle is-running' : 'capture-toggle'}
            onClick={toggleCapture}
            disabled={!online || !status}
          >
            <Pause className="capture-pause-icon" />
            <Play className="capture-play-icon" />
            <span className="capture-pause-label">Pause</span>
            <span className="capture-play-label">Start</span>
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
              Tune the bottom dialogue box and the upper-right tutorial banner independently.
            </DialogDescription>
          </DialogHeader>

          <div className="capture-tabs" role="tablist" aria-label="Capture region">
            <button
              type="button"
              className={setupChannel === 'dialogue' ? 'is-active' : ''}
              onClick={() => setSetupChannel('dialogue')}
            >
              <MessageSquareText size={16} /> Dialogue
            </button>
            <button
              type="button"
              className={setupChannel === 'tip' ? 'is-active' : ''}
              onClick={() => setSetupChannel('tip')}
            >
              <ScanLine size={16} /> Top-right tips
            </button>
            <button
              type="button"
              className={setupChannel === 'cinematic' ? 'is-active' : ''}
              onClick={() => setSetupChannel('cinematic')}
            >
              <Volume2 size={16} /> Cutscenes & comics
            </button>
          </div>

          <div className="capture-preview">
            {(setupChannel === 'tip' ? capture?.tip_crop_bounds : setupChannel === 'cinematic' ? capture?.cinematic_crop_bounds : capture?.crop_bounds) ? (
              <img
                key={previewTick}
                src={`${API_URL}/api/capture/preview.jpg?${previewRegionQuery}`}
                alt={`Live preview of the ${setupChannel === 'tip' ? 'top-right tip' : setupChannel === 'cinematic' ? 'cinematic and comic' : 'dialogue'} capture region`}
              />
            ) : (
              <div className="preview-placeholder"><ScanLine /> Start the selected game to see the capture preview.</div>
            )}
            <span>{setupChannel === 'tip' ? 'Top-right live crop' : setupChannel === 'cinematic' ? 'Cutscene / comic live crop' : 'Dialogue live crop'}</span>
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
                  <span>{label}<strong>{Math.round((setupChannel === 'tip' ? draftSettings.tip_region : setupChannel === 'cinematic' ? draftSettings.cinematic_region : draftSettings.region)[field] * 100)}%</strong></span>
                  <input
                    type="range"
                    min={field === 'width' || field === 'height' ? 5 : 0}
                    max={100}
                    step={1}
                    value={Math.round((setupChannel === 'tip' ? draftSettings.tip_region : setupChannel === 'cinematic' ? draftSettings.cinematic_region : draftSettings.region)[field] * 100)}
                    onChange={(event) => updateRegion(field, Number(event.target.value))}
                  />
                </label>
              ))}
            </div>
          ) : null}

          <div className="ocr-readout">
            <span>Latest OCR</span>
            <StableText text={(setupChannel === 'tip' ? capture?.last_tip_ocr : setupChannel === 'cinematic' ? capture?.last_cinematic_ocr : capture?.last_ocr) || 'No English text detected in the current region.'} />
            <small><StableInline text={(setupChannel === 'tip' ? capture?.last_tip_ocr_confidence : setupChannel === 'cinematic' ? capture?.last_cinematic_ocr_confidence : capture?.last_ocr_confidence) ? `${Math.round((setupChannel === 'tip' ? capture?.last_tip_ocr_confidence : setupChannel === 'cinematic' ? capture?.last_cinematic_ocr_confidence : capture?.last_ocr_confidence) ?? 0)}% OCR confidence` : 'Waiting for text'} /></small>
          </div>

          <div className="setup-actions">
            <Button variant="outline" onClick={refreshTextMaps} disabled={refreshingMaps}>
              <RefreshCw className={refreshingMaps ? 'is-spinning' : ''} />
              <StableInline text={refreshingMaps ? 'Updating…' : 'Update TextMaps'} />
            </Button>
            <Button onClick={saveSettings} disabled={!draftSettings || saving}>
              <StableInline text={saving ? 'Saving…' : 'Save both regions'} />
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
