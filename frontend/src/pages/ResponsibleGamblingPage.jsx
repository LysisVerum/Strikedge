import LegalNav from '../components/LegalNav';

export default function ResponsibleGamblingPage() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <LegalNav />
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '5.5rem 1.5rem 4rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.5px', marginBottom: '0.5rem' }}>Responsible Gambling</h1>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.7, marginBottom: '2.5rem' }}>
          StrikeEdge is a data and analytics tool. We take problem gambling seriously and encourage all users to gamble responsibly.
        </p>

        <div style={{ borderRadius: 14, border: '1px solid rgba(239,68,68,0.25)', background: 'rgba(239,68,68,0.06)', padding: '1.25rem 1.5rem', marginBottom: '2rem' }}>
          <p style={{ fontSize: '0.9rem', color: '#ef4444', fontWeight: 600, marginBottom: '0.3rem' }}>Need help?</p>
          <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            If you or someone you know has a gambling problem, free help is available 24/7:<br />
            <strong style={{ color: 'var(--text-primary)' }}>1-800-GAMBLER</strong> (1-800-426-2537) — US<br />
            <strong style={{ color: 'var(--text-primary)' }}>1-866-531-2600</strong> — Canada (ConnexOntario)<br />
            <a href="https://www.ncpgambling.org" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-blue)' }}>ncpgambling.org</a>
          </p>
        </div>

        <Section title="Warning Signs">
          Gambling may be becoming a problem if you: bet more than you can afford to lose, chase losses, neglect work or family due to gambling, feel anxious or irritable when not gambling, or borrow money to gamble.
        </Section>

        <Section title="Set Limits">
          Always set a budget before placing any bets and stick to it. Never bet money you cannot afford to lose. Treat betting as entertainment, not a source of income.
        </Section>

        <Section title="Take Breaks">
          If you feel like gambling is taking up too much of your time or money, take a break. Most sportsbooks offer self-exclusion and deposit limit tools — use them.
        </Section>

        <Section title="Our Commitment">
          StrikeEdge provides analysis for informational purposes only. We do not facilitate betting directly. If you believe you have a gambling problem, please seek help before continuing to use any gambling-related service.
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: '2rem' }}>
      <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.6rem' }}>{title}</h2>
      <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.7 }}>{children}</p>
    </div>
  );
}
