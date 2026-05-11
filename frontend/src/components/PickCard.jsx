import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ExternalLink } from 'lucide-react';
import PickDetail from './PickDetail';
import PitcherCard from './PitcherCard';

// PropOdds returns display names like "DraftKings", "FanDuel" — keyed both ways
const BOOK_URLS = {
  'draftkings':   'https://sportsbook.draftkings.com/leagues/baseball/mlb',
  'DraftKings':   'https://sportsbook.draftkings.com/leagues/baseball/mlb',
  'fanduel':      'https://sportsbook.fanduel.com/baseball/mlb',
  'FanDuel':      'https://sportsbook.fanduel.com/baseball/mlb',
  'betmgm':       'https://sports.betmgm.com/en/sports/baseball-23',
  'BetMGM':       'https://sports.betmgm.com/en/sports/baseball-23',
  'caesars':      'https://sportsbook.caesars.com/us/va/baseball/mlb',
  'Caesars':      'https://sportsbook.caesars.com/us/va/baseball/mlb',
  'pointsbet':    'https://pointsbet.com/sports/baseball/MLB',
  'PointsBet':    'https://pointsbet.com/sports/baseball/MLB',
  'betrivers':    'https://pa.betrivers.com/?page=sportsbook#baseball/mlb',
  'BetRivers':    'https://pa.betrivers.com/?page=sportsbook#baseball/mlb',
  'bovada':       'https://www.bovada.lv/sports/baseball/mlb',
  'Bovada':       'https://www.bovada.lv/sports/baseball/mlb',
};

const BOOK_LABELS = {}; // use the book name as-is from the API

function BookLink({ book, style = {} }) {
  const url   = BOOK_URLS[book];
  const label = book;
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={e => e.stopPropagation()}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
        fontSize: '0.7rem', color: 'var(--accent-blue)',
        textDecoration: 'none', fontWeight: 600,
        padding: '2px 8px', borderRadius: 6,
        border: '1px solid rgba(29,155,240,0.25)',
        background: 'rgba(29,155,240,0.07)',
        transition: 'background 0.15s',
        ...style,
      }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(29,155,240,0.15)'}
      onMouseLeave={e => e.currentTarget.style.background = 'rgba(29,155,240,0.07)'}
    >
      {label} <ExternalLink size={10} />
    </a>
  );
}

const CONF_COLORS = {
  HIGH:   { bg: 'rgba(0,200,83,0.10)',   border: 'rgba(0,200,83,0.28)',   text: '#00c853' },
  MEDIUM: { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.28)', text: '#f59e0b' },
  LOW:    { bg: 'rgba(139,148,158,0.10)',border: 'rgba(139,148,158,0.28)','text': '#8b949e' },
};

const REC_COLORS = {
  OVER:  'var(--accent-green)',
  UNDER: 'var(--accent-red)',
  PASS:  'var(--text-muted)',
};

function NoLineCard({ pick, index }) {
  const [open, setOpen] = useState(false);
  const [cardOpen, setCardOpen] = useState(false);
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
        {/* Rank slot — dash for no-line */}
        <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-muted)', textAlign: 'center' }}>
          –
        </div>

        {/* Main info */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
            <button
              onClick={e => { e.stopPropagation(); setCardOpen(true); }}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)', textDecoration: 'underline dotted', textUnderlineOffset: 3 }}
            >
              {pick.pitcher_name}
            </button>
            <span style={{
              fontSize: '0.68rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
              background: 'rgba(139,148,158,0.10)', border: '1px solid rgba(139,148,158,0.25)',
              color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
            }}>
              No line
            </span>
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            {pick.matchup}
          </div>
        </div>

        {/* Predicted Ks — only data we can show */}
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.3rem', fontWeight: 900, color: 'var(--text-secondary)', fontFamily: 'Space Grotesk, sans-serif', lineHeight: 1 }}>
            ~{pick.predicted_ks}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>proj K</div>
        </div>

        {/* Chevron */}
        <motion.div animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown size={16} color="var(--text-muted)" />
        </motion.div>
      </div>

      <AnimatePresence>
        {open && <PickDetail key="detail" pick={pick} />}
      </AnimatePresence>
      {cardOpen && <PitcherCard pick={pick} onClose={() => setCardOpen(false)} />}
    </motion.div>
  );
}

export default function PickCard({ pick, index }) {
  const [open, setOpen] = useState(false);
  const [cardOpen, setCardOpen] = useState(false);

  if (!pick.has_line) return <NoLineCard pick={pick} index={index} />;

  const conf = CONF_COLORS[pick.confidence] ?? CONF_COLORS.LOW;
  const edgeVal = parseFloat(pick.edge_pct_display);
  const edgeColor = edgeVal >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const modelPct   = Math.round(pick.model_prob_over * 100);
  const impliedPct = Math.round(pick.implied_prob_over * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07, duration: 0.4 }}
      style={{
        borderRadius: 12,
        border: `1px solid ${open ? conf.border : 'var(--border)'}`,
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
            <button
              onClick={e => { e.stopPropagation(); setCardOpen(true); }}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)', textDecoration: 'underline dotted', textUnderlineOffset: 3 }}
            >
              {pick.pitcher_name}
            </button>
            <span style={{
              fontSize: '0.68rem', fontWeight: 700, padding: '2px 7px', borderRadius: 999,
              background: conf.bg, border: `1px solid ${conf.border}`, color: conf.text,
              textTransform: 'uppercase', letterSpacing: '0.05em',
            }}>
              {pick.confidence}
            </span>
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.45rem' }}>
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
          {pick.live_line ? (
            <div style={{ marginBottom: '0.4rem' }}>
              <BookLink book={pick.line_source} />
            </div>
          ) : (
            <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>
              model-projected line
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{ flex: 1, height: 3, borderRadius: 3, background: 'var(--border)', overflow: 'hidden', maxWidth: 180 }}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${modelPct}%` }}
                transition={{ delay: index * 0.07 + 0.3, duration: 0.7, ease: 'easeOut' }}
                style={{ height: '100%', background: `linear-gradient(90deg, ${edgeColor}, var(--accent-blue))`, borderRadius: 3 }}
              />
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              {modelPct}% · implied {impliedPct}%
            </span>
          </div>
        </div>

        {/* Edge + bet size */}
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 900, color: edgeColor, fontFamily: 'Space Grotesk, sans-serif', lineHeight: 1 }}>
            {pick.edge_pct_display}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>edge</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 3, fontWeight: 600 }}>~{pick.predicted_ks} K</div>
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
        {open && <PickDetail key="detail" pick={pick} />}
      </AnimatePresence>
      {cardOpen && <PitcherCard pick={pick} onClose={() => setCardOpen(false)} />}
    </motion.div>
  );
}
