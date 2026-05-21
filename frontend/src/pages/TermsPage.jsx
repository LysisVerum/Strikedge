import { Link } from 'react-router-dom';
import { TrendingUp } from 'lucide-react';

function LegalNav() {
  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 2rem', height: '60px',
      background: 'rgba(8,12,16,0.9)', backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--border)',
    }}>
      <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', textDecoration: 'none' }}>
        <div style={{ width: 26, height: 26, borderRadius: 6, background: 'linear-gradient(135deg,#1d9bf0,#0066cc)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <TrendingUp size={14} color="#fff" />
        </div>
        <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
          Strike<span style={{ color: 'var(--accent-blue)' }}>Edge</span>
        </span>
      </Link>
    </nav>
  );
}

export default function TermsPage() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <LegalNav />
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '5.5rem 1.5rem 4rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.5px', marginBottom: '0.5rem' }}>Terms of Service</h1>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '2.5rem' }}>Last updated: May 2026</p>

        <Section title="Entertainment Purposes Only">
          StrikeEdge provides statistical analysis and data-driven insights for entertainment and informational purposes only. Nothing on this platform constitutes financial advice, investment advice, or a recommendation to place any bet or wager.
        </Section>

        <Section title="No Guarantee of Accuracy">
          Our models are based on historical data and statistical methods. Past performance is not indicative of future results. We make no guarantees regarding the accuracy, completeness, or profitability of any analysis provided.
        </Section>

        <Section title="Eligibility">
          You must be of legal age in your jurisdiction to use this service. It is your responsibility to ensure that online sports betting analytics services are lawful in your region.
        </Section>

        <Section title="Subscriptions">
          Premium subscriptions are billed monthly. You may cancel at any time and will retain access until the end of your current billing period. Refunds are not provided for partial billing periods.
        </Section>

        <Section title="Account Responsibility">
          You are responsible for maintaining the security of your account. StrikeEdge is not liable for any loss resulting from unauthorized access to your account.
        </Section>

        <Section title="Modifications">
          We reserve the right to modify these terms at any time. Continued use of the service after changes constitutes acceptance of the updated terms.
        </Section>

        <Section title="Contact">
          Questions about these terms? Email us at <a href="mailto:nich8804@gmail.com" style={{ color: 'var(--accent-blue)' }}>nich8804@gmail.com</a>.
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
