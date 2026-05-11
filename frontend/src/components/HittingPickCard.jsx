import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';

const BOOK_URLS = {
  'DraftKings':  'https://sportsbook.draftkings.com/leagues/baseball/mlb',
  'draftkings':  'https://sportsbook.draftkings.com/leagues/baseball/mlb',
  'FanDuel':     'https://sportsbook.fanduel.com/baseball/mlb',
  'fanduel':     'https://sportsbook.fanduel.com/baseball/mlb',
  'BetMGM':      'https://sports.betmgm.com/en/sports/baseball-23',
  'betmgm':      'https://sports.betmgm.com/en/sports/baseball-23',
  'Caesars':     'https://sportsbook.caesars.com/us/va/baseball/mlb',
  'caesars':     'https://sportsbook.caesars.com/us/va/baseball/mlb',
  'BetRivers':   'https://pa.betrivers.com/?page=sportsbook#baseball/mlb',
  'betrivers':   'https://pa.betrivers.com/?page=sportsbook#baseball/mlb',
  'Fanatics':    'https://sportsbook.fanaticssportsbook.com/sports/baseball/mlb',
  'fanatics':    'https://sportsbook.fanaticssportsbook.com/sports/baseball/mlb',
  'BetOnline.ag':'https://www.betonline.ag/sportsbook/baseball/mlb',
};

function BookLink({ book }) {
  const url = BOOK_URLS[book];
  if (!book || !url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={e => e.stopPropagation()}
      style={{
        fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: 6,
        background: 'rgba(29,155,240,0.08)', border: '1px solid rgba(29,155,240,0.25)',
        color: 'var(--accent-blue)', textDecoration: 'none', display: 'inline-block',
      }}
    >
      {book}
    </a>
  );
}

// Amber/orange palette for hitting section
const ACCENT = '#f97316';
const ACCENT_BG = 'rgba(249,115,22,0.10)';
const ACCENT_BORDER = 'rgba(249,115,22,0.28)';

const CONF_COLORS = {
  HIGH:   { bg: 'rgba(0,200,83,0.10)',   border: 'rgba(0,200,83,0.28)',   text: '#00c853' },
  MEDIUM: { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.28)', text: '#f59e0b' },
  LOW:    { bg: 'rgba(139,148,158,0.10)',border: 'rgba(139,148,158,0.28)', text: '#8b949e' },
};

const REC_COLORS = {
  OVER:  'var(--accent-green)',
  UNDER: 'var(--accent-red)',
  PASS:  'var(--text-muted)',
};

function StatBar({ label, value, max, color = ACCENT, format = (v) => `${(v * 100).toFixed(1)}%` }) {
  const missing = value == null || isNaN(value);
  const pct = missing ? 0 : Math.min((value / max) * 100, 100);
  return (
    <div style={{ marginBottom: '0.6rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{label}</span>
        <span style={{ fontSize: '0.75rem', fontWeight: 700, color: missing ? 'var(--text-muted)' : color }}>
          {missing ? '—' : format(value)}
        </span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: 'var(--border)', overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          style={{ height: '100%', background: missing ? 'var(--border)' : color, borderRadius: 3 }}
        />
      </div>
    </div>
  );
}

function Chip({ label, value, color = 'var(--text-secondary)' }) {
  return (
    <div style={{
      padding: '0.4rem 0.75rem', borderRadius: 8,
      border: '1px solid var(--border)', background: 'var(--bg-secondary)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
    }}>
      <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{label}</span>
      <span style={{ fontSize: '0.9rem', fontWeight: 700, color }}>{value}</span>
    </div>
  );
}

function HittingPickDetail({ pick }) {
  const f = pick.features ?? {};
  const edgeColor = (pick.edge_pct ?? 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const isUnder = pick.recommendation === 'UNDER';
  const modelProbLabel   = isUnder ? 'Model P(Under)'   : 'Model P(Over)';
  const impliedProbLabel = isUnder ? 'Implied P(Under)' : 'Implied P(Over)';
  const modelProbVal   = pick.model_prob_over   != null ? (isUnder ? 1 - pick.model_prob_over   : pick.model_prob_over)   : null;
  const impliedProbVal = pick.implied_prob_over != null ? (isUnder ? 1 - pick.implied_prob_over : pick.implied_prob_over) : null;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.28 }}
      style={{ overflow: 'hidden' }}
    >
      <div style={{
        padding: '1.25rem 1.5rem 1.5rem',
        borderTop: `1px solid ${ACCENT_BORDER}`,
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '1.5rem',
      }}>

        {/* Hit rate trend */}
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>Hit Rate Trend</p>
          <StatBar label="Last 7 days"  value={f.h7}  max={0.45} color={ACCENT} />
          <StatBar label="Last 14 days" value={f.h14} max={0.45} color={ACCENT} />
          <StatBar label="Last 30 days" value={f.h30} max={0.45} color="rgba(249,115,22,0.6)" />
          <StatBar label="Season"       value={f.hs}  max={0.45} color="var(--text-secondary)" />
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            vs this hand (last 60d):&nbsp;
            <span style={{ color: f.vs_hand != null ? ACCENT : 'var(--text-muted)', fontWeight: 600 }}>
              {f.vs_hand != null ? `${(f.vs_hand * 100).toFixed(1)}%` : '—'}
            </span>
          </div>
        </div>

        {/* Contact quality */}
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>Contact Quality (30d)</p>
          <StatBar label="Sweet spot %" value={f.sweet_spot} max={0.50} color="#a855f7" />
          <StatBar label="Hard hit %"   value={f.hard_hit}  max={0.70} color="#f97316" />
          <StatBar label="Barrel rate"  value={f.barrel}    max={0.20} color="#ef4444" />
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <span>xBA: <span style={{ color: f.xba != null ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600 }}>{f.xba != null ? f.xba.toFixed(3) : '—'}</span></span>
            <span>Exit velo: <span style={{ color: f.exit_velo != null ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 600 }}>{f.exit_velo != null ? `${f.exit_velo.toFixed(1)} mph` : '—'}</span></span>
          </div>
        </div>

        {/* Matchup context + model math */}
        <div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>Matchup Context</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '1rem' }}>
            <Chip label="Opp K%"      value={f.opp_k != null ? `${(f.opp_k * 100).toFixed(1)}%` : '—'}         color="var(--accent-amber)" />
            <Chip label="Opp xBA alw" value={f.opp_xba != null ? f.opp_xba.toFixed(3) : '—'}                   color="var(--accent-amber)" />
            <Chip label="PA / game"   value={f.pa_rate != null ? f.pa_rate.toFixed(1) : '—'}                    color="var(--text-secondary)" />
            <Chip label="Park factor" value={f.park != null ? f.park.toFixed(2) : '—'}                          color="var(--text-secondary)" />
          </div>

          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.6rem' }}>Model Output</p>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: 4 }}>
            <span style={{ color: 'var(--text-secondary)' }}>Predicted Hits</span>
            <span style={{ fontWeight: 700 }}>{pick.predicted_hits}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: 4 }}>
            <span style={{ color: 'var(--text-secondary)' }}>{modelProbLabel}</span>
            <span style={{ fontWeight: 700, color: ACCENT }}>
              {modelProbVal != null ? `${(modelProbVal * 100).toFixed(1)}%` : '—'}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: 4 }}>
            <span style={{ color: 'var(--text-secondary)' }}>{impliedProbLabel}</span>
            <span style={{ fontWeight: 700, color: 'var(--text-muted)' }}>
              {impliedProbVal != null ? `${(impliedProbVal * 100).toFixed(1)}%` : '—'}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Edge</span>
            <span style={{ fontWeight: 800, color: edgeColor }}>{pick.edge_pct_display}</span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function NoLineBatterCard({ pick, index }) {
  const [open, setOpen] = useState(false);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.4 }}
      style={{
        borderRadius: 12,
        border: '1px solid var(--border)',
        background: 'var(--bg-card)',
        overflow: 'hidden',
        opacity: 0.72,
      }}
    >
      <div
        onClick={() => setOpen(v => !v)}
        style={{
          padding: '1.1rem 1.5rem',
          display: 'grid',
          gridTemplateColumns: '2rem 1fr auto 1.5rem',
          gap: '1rem',
          alignItems: 'center',
          cursor: 'pointer',
          userSelect: 'none',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-card-hover)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-muted)', textAlign: 'center' }}>–</div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>{pick.batter_name}</span>
            <span style={{
              fontSize: '0.68rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
              background: 'rgba(139,148,158,0.10)', border: '1px solid rgba(139,148,158,0.25)',
              color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
            }}>No line</span>
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>{pick.matchup}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.3rem', fontWeight: 900, color: 'var(--text-secondary)', fontFamily: 'Space Grotesk, sans-serif', lineHeight: 1 }}>
            ~{pick.predicted_hits}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>proj H</div>
        </div>
        <motion.div animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown size={16} color="var(--text-muted)" />
        </motion.div>
      </div>
      <AnimatePresence>
        {open && <HittingPickDetail key="detail" pick={pick} />}
      </AnimatePresence>
    </motion.div>
  );
}

export default function HittingPickCard({ pick, index }) {
  const [open, setOpen] = useState(false);
  if (pick.has_line === false) return <NoLineBatterCard pick={pick} index={index} />;

  const conf = CONF_COLORS[pick.confidence] ?? CONF_COLORS.LOW;
  const edgeVal    = parseFloat(pick.edge_pct_display);
  const edgeColor  = edgeVal >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const isUnder    = pick.recommendation === 'UNDER';
  const modelPct   = isUnder
    ? Math.round((1 - pick.model_prob_over) * 100)
    : Math.round(pick.model_prob_over * 100);
  const impliedPct = isUnder
    ? Math.round((1 - pick.implied_prob_over) * 100)
    : Math.round(pick.implied_prob_over * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.4 }}
      style={{
        borderRadius: 12,
        border: `1px solid ${open ? ACCENT_BORDER : 'var(--border)'}`,
        background: 'var(--bg-card)',
        overflow: 'hidden',
        transition: 'border-color 0.2s',
      }}
    >
      {/* Summary row */}
      <div
        onClick={() => setOpen(v => !v)}
        style={{
          padding: '1.1rem 1.5rem',
          display: 'grid',
          gridTemplateColumns: '2rem 1fr auto 1.5rem',
          gap: '1rem',
          alignItems: 'center',
          cursor: 'pointer',
          userSelect: 'none',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-card-hover)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        {/* Rank */}
        <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-muted)', fontFamily: 'Space Grotesk, sans-serif', textAlign: 'center' }}>
          {pick.rank}
        </div>

        {/* Main info */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
              {pick.batter_name}
            </span>
            <span style={{
              fontSize: '0.68rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
              background: conf.bg, border: `1px solid ${conf.border}`, color: conf.text,
              textTransform: 'uppercase', letterSpacing: '0.05em',
            }}>
              {pick.confidence}
            </span>
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
            <span style={{ color: REC_COLORS[pick.recommendation], fontWeight: 700 }}>{pick.bet}</span>
            {pick.recommendation === 'PASS' && pick.over_odds != null && pick.under_odds != null ? (
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                O {pick.over_odds > 0 ? '+' : ''}{pick.over_odds} / U {pick.under_odds > 0 ? '+' : ''}{pick.under_odds}
              </span>
            ) : pick.recommendation === 'UNDER' && pick.under_odds != null ? (
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                ({pick.under_odds > 0 ? '+' : ''}{pick.under_odds})
              </span>
            ) : pick.over_odds != null ? (
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                ({pick.over_odds > 0 ? '+' : ''}{pick.over_odds})
              </span>
            ) : null}
            &nbsp;·&nbsp;{pick.matchup}
          </div>
          {pick.line_source && pick.line_source !== 'model' && (
            <div style={{ marginBottom: '0.35rem' }}>
              <BookLink book={pick.line_source} />
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{ flex: 1, height: 3, borderRadius: 3, background: 'var(--border)', overflow: 'hidden', maxWidth: 180 }}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${modelPct}%` }}
                transition={{ delay: index * 0.07 + 0.3, duration: 0.7, ease: 'easeOut' }}
                style={{ height: '100%', background: `linear-gradient(90deg, ${edgeColor}, ${ACCENT})`, borderRadius: 3 }}
              />
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              {modelPct}% · implied {impliedPct}%
            </span>
          </div>
        </div>

        {/* Edge + stats */}
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 900, color: edgeColor, fontFamily: 'Space Grotesk, sans-serif', lineHeight: 1 }}>
            {pick.edge_pct_display}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>edge</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 3, fontWeight: 600 }}>~{pick.predicted_hits} H</div>
          {pick.recommended_bet > 0 && (
            <div style={{
              marginTop: 6, fontSize: '0.72rem', fontWeight: 700,
              color: edgeColor, padding: '2px 7px', borderRadius: 6,
              background: edgeVal >= 0 ? 'rgba(0,200,83,0.10)' : 'rgba(239,68,68,0.10)',
              border: `1px solid ${edgeVal >= 0 ? 'rgba(0,200,83,0.25)' : 'rgba(239,68,68,0.25)'}`,
              display: 'inline-block',
            }}>
              ${pick.recommended_bet}
            </div>
          )}
        </div>

        {/* Chevron */}
        <motion.div animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown size={16} color="var(--text-muted)" />
        </motion.div>
      </div>

      <AnimatePresence>
        {open && <HittingPickDetail key="detail" pick={pick} />}
      </AnimatePresence>
    </motion.div>
  );
}
