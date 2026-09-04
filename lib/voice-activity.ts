export type VoiceActivity = { kind: 'history' | 'agents'; occurred_at: number };

export function createVoiceActivityFollower(
  changeTab: (tab: 'history' | 'agents') => void,
  openedAt = 0,
) {
  let lastSeen = openedAt;
  return (activity?: VoiceActivity | null) => {
    if (!activity || !['history', 'agents'].includes(activity.kind)
      || !Number.isFinite(activity.occurred_at) || activity.occurred_at <= lastSeen) return;
    lastSeen = activity.occurred_at;
    changeTab(activity.kind);
  };
}
