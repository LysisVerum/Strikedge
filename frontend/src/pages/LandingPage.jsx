import { Helmet } from 'react-helmet-async';
import Navbar from '../components/Navbar';
import Hero from '../sections/Hero';
import Features from '../sections/Features';
import HowItWorks from '../sections/HowItWorks';
import Footer from '../sections/Footer';

export default function LandingPage() {
  return (
    <>
      <Helmet>
        <title>StrikeEdge — MLB Prop Betting Analytics</title>
        <meta name="description" content="Data-driven MLB strikeout and hit prop picks. StrikeEdge uses statistical models to find edges on pitcher strikeout props and batter hit props — updated daily." />
        <link rel="canonical" href="https://www.strikedge.ca" />
      </Helmet>
      <Navbar />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
      </main>
      <Footer />
    </>
  );
}
