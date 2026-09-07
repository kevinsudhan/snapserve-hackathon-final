import { useState } from 'react'
import { toast } from 'sonner'
import {
  BookOpenCheck,
  Copy,
  Database,
  ExternalLink,
  FileCode2,
  Map as MapIcon,
  RefreshCw,
  Waves,
} from 'lucide-react'
import { useGeo, useKnowledgeStatus, usePrompt, useRefreshKnowledge, useSnapshot } from '@/lib/api'
import { alertTone } from '@/lib/tone'
import { ago, copyText, fmtDate, fmtDateTime, nf } from '@/lib/utils'
import { Badge, Button, EmptyState, Panel, PanelHeader, Skeleton, toneVars } from '@/components/ui/base'
import { CountUp } from '@/components/ui/CountUp'
import { Drawer } from '@/components/ui/overlays'
import { TnMap } from '@/components/map/TnMap'

export default function Knowledge() {
  const { data: status, isLoading } = useKnowledgeStatus()
  const { data: snapshot } = useSnapshot()
  const { data: geo, isLoading: geoLoading, isError: geoError } = useGeo()
  const [promptOpen, setPromptOpen] = useState(false)
  const { data: prompt } = usePrompt(promptOpen)
  const refresh = useRefreshKnowledge()

  const doRefresh = () => {
    const id = toast.loading('Pulling 60 days of Open-Meteo + GDACS, re-rendering the prompt…')
    refresh.mutate(undefined, {
      onSuccess: (s) =>
        toast.success('Snapshot refreshed and pushed to the agent', {
          id,
          description: `${s.districts} districts · ${nf(s.approx_tokens)} tokens in the prompt`,
        }),
      onError: () => toast.error('Refresh failed — the snapshot on disk is unchanged', { id }),
    })
  }

  return (
    <div className="space-y-4">
      {/* status strip */}
      <Panel className="flex flex-wrap items-center gap-x-8 gap-y-4 px-5 py-4">
        {isLoading || !status ? (
          <Skeleton className="h-12 w-full" />
        ) : (
          <>
            <Stat label="Districts" value={status.districts} hint="Tamil Nadu, from tn_districts.json" />
            <Stat label="Days covered" value={status.days} hint="one pull, no runtime fetching" />
            <Stat label="Notable events" value={status.notable_events} hint="days the agent may quote" />
            <Stat
              label="Prompt size"
              value={status.approx_tokens}
              hint="approximate tokens in the system prompt"
            />
            <div className="min-w-0">
              <div className="eyebrow mb-1.5">Freshness</div>
              <div className="space-y-0.5 text-[12px] text-[var(--fg-muted)]">
                <div>
                  snapshot <span className="mono">{ago(status.last_refresh_at)}</span>
                </div>
                <div>
                  agent synced <span className="mono">{ago(status.agent_synced_at)}</span>
                </div>
              </div>
            </div>

            <div className="ml-auto flex items-center gap-2">
              <Button icon={<FileCode2 size={14} />} onClick={() => setPromptOpen(true)}>
                Prompt preview
              </Button>
              <Button
                variant="primary"
                icon={<RefreshCw size={14} className={refresh.isPending ? 'animate-spin' : ''} />}
                onClick={doRefresh}
                disabled={refresh.isPending}
              >
                {refresh.isPending ? 'Refreshing…' : 'Refresh snapshot & sync agent'}
              </Button>
            </div>
          </>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.15fr_1fr]">
        {/* map */}
        <Panel className="overflow-hidden">
          <PanelHeader
            eyebrow="Snapshot"
            title="Tamil Nadu · 7-day rainfall"
            icon={<MapIcon size={14} />}
            tone="sky"
            right={
              snapshot && <Badge tone="sky">generated {fmtDateTime(snapshot.generated_at)}</Badge>
            }
          />
          <div className="px-4 pb-4">
            {geoLoading && <Skeleton className="h-[560px] rounded-[11px]" />}
            {geoError && (
              <EmptyState
                icon={<MapIcon size={17} />}
                title="District boundaries unavailable"
                hint="GET /api/knowledge/geo did not return a GeoJSON FeatureCollection."
              />
            )}
            {geo && <TnMap geo={geo} snapshot={snapshot} />}
          </div>
        </Panel>

        <div className="space-y-4">
          {/* disasters */}
          <Panel>
            <PanelHeader
              eyebrow="GDACS"
              title="Notable disaster events in the window"
              icon={<Waves size={14} />}
              tone="violet"
              right={<Badge tone="violet">{snapshot?.disasters.length ?? 0}</Badge>}
            />
            <div className="space-y-2 px-5 pb-5">
              {(snapshot?.disasters ?? []).map((e) => {
                const t = toneVars[alertTone(e.alert_level)]
                return (
                  <a
                    key={e.id}
                    href={e.report_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="group flex items-center gap-3 rounded-[10px] border px-3 py-2.5 transition-colors duration-150 hover:border-[var(--line-strong)]"
                    style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)' }}
                  >
                    <span className="h-8 w-[3px] shrink-0 rounded-full" style={{ background: t.fg }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-medium">{e.name}</span>
                      <span className="mono block text-[11px] text-[var(--fg-subtle)]">
                        {e.id} · {fmtDate(e.from)} → {fmtDate(e.to)}
                      </span>
                    </span>
                    <Badge tone={alertTone(e.alert_level)}>{e.alert_level}</Badge>
                    <ExternalLink size={12} className="shrink-0 text-[var(--fg-subtle)]" />
                  </a>
                )
              })}
              {(!snapshot || snapshot.disasters.length === 0) && (
                <EmptyState
                  icon={<Waves size={16} />}
                  title="No disaster events in the window"
                  hint="Nothing from GDACS within the snapshot period for Tamil Nadu."
                  className="py-8"
                />
              )}
            </div>
          </Panel>

          {/* sources */}
          <Panel>
            <PanelHeader
              eyebrow="Provenance"
              title="Sources behind every quoted fact"
              icon={<Database size={14} />}
              tone="teal"
              right={<Badge tone="teal">{status?.sources.length ?? 0}</Badge>}
            />
            <ul className="px-5 pb-5">
              {(status?.sources ?? []).map((s, i) => (
                <li
                  key={s.id}
                  className="flex items-start gap-3 py-2.5"
                  style={{ borderTop: i === 0 ? 'none' : '1px solid var(--line)' }}
                >
                  <span
                    className="mono mt-0.5 shrink-0 rounded-[5px] border px-1.5 py-0.5 text-[10px]"
                    style={{ borderColor: 'var(--line-strong)', color: 'var(--fg-subtle)' }}
                  >
                    {s.kind}
                  </span>
                  <span className="min-w-0 flex-1">
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="block truncate text-[12.5px] font-medium hover:text-[var(--accent-fg)] hover:underline"
                    >
                      {s.title}
                    </a>
                    <span className="block truncate text-[11px] text-[var(--fg-subtle)]">
                      {s.publisher} · as of {fmtDate(s.as_of)}
                    </span>
                  </span>
                  <ExternalLink size={12} className="mt-1 shrink-0 text-[var(--fg-subtle)]" />
                </li>
              ))}
              {!status && <Skeleton className="h-24" />}
            </ul>
          </Panel>
        </div>
      </div>

      {/* prompt drawer */}
      <Drawer
        open={promptOpen}
        onOpenChange={setPromptOpen}
        title="System prompt sent to the agent"
        description={
          prompt
            ? `${nf(prompt.approx_tokens)} tokens · rendered from the snapshot, the scheme facts and the safe scripts`
            : 'Loading…'
        }
        width={720}
      >
        <div className="p-5">
          <div className="mb-3 flex items-center gap-2">
            <Badge tone="neutral" mono>
              <BookOpenCheck size={11} />
              knowledge.render → PATCH /api/agents/1151
            </Badge>
            <Button
              size="xs"
              className="ml-auto"
              icon={<Copy size={12} />}
              onClick={async () => {
                await copyText(prompt?.system_prompt ?? '')
                toast.success('Prompt copied')
              }}
            >
              Copy
            </Button>
          </div>
          {prompt ? (
            <pre
              className="mono max-h-[calc(100dvh-190px)] overflow-auto rounded-[11px] border p-4 text-[11.5px] leading-relaxed whitespace-pre-wrap"
              style={{ background: 'var(--surface-inset)', borderColor: 'var(--line)', color: 'var(--fg-muted)' }}
            >
              {prompt.system_prompt}
            </pre>
          ) : (
            <Skeleton className="h-[420px] rounded-[11px]" />
          )}
        </div>
      </Drawer>
    </div>
  )
}

function Stat({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="min-w-0">
      <div className="eyebrow mb-1.5">{label}</div>
      <div className="display text-[26px] leading-none">
        <CountUp value={value} />
      </div>
      <div className="mt-1.5 truncate text-[11px] text-[var(--fg-subtle)]">{hint}</div>
    </div>
  )
}
