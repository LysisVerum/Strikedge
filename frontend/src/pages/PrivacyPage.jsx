import LegalNav from '../components/LegalNav';

export default function PrivacyPage() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <LegalNav />
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '5.5rem 1.5rem 4rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, letterSpacing: '-0.5px', marginBottom: '0.5rem' }}>Privacy Policy</h1>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '2.5rem' }}>Last updated: May 2026</p>

        <Section title="Information We Collect">
          We collect only what is necessary to operate the service. This includes your email address (used for authentication via magic link) and basic usage data such as which features you access.
        </Section>

        <Section title="How We Use Your Information">
          Your email is used solely to send authentication links and subscription-related communications. We do not sell, rent, or share your personal information with third parties for marketing purposes.
        </Section>

        <Section title="Subscription & Payments">
          Payment processing is handled by Stripe. StrikeEdge does not store your payment card details. Stripe's privacy policy governs the handling of your payment information.
        </Section>

        <Section title="Data Storage">
          Your account information (email, subscription status) is stored securely. We retain your data for as long as your account is active or as required by law.
        </Section>

        <Section title="Cookies">
          We use a session token stored in your browser's local storage to keep you logged in. We do not use third-party tracking cookies.
        </Section>

        <Section title="Contact">
          For privacy-related questions, contact us at <a href="mailto:nich8804@gmail.com" style={{ color: 'var(--accent-blue)' }}>nich8804@gmail.com</a>.
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
