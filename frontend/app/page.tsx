import Link from "next/link";
import { Activity, ArrowRight, BarChart3, CloudRain, Cross, ShieldCheck, Sparkles, Trophy } from "lucide-react";
import type { Metadata } from "next";

export const dynamic="force-dynamic";
export const metadata:Metadata={title:"Fourth Down | Free ESPN Fantasy Football Decision Engine",description:"Connect your ESPN fantasy league and get explainable lineup, waiver, trade, and draft recommendations using simulations, free weather data, and Vegas game context.",alternates:{canonical:"/"},openGraph:{title:"Fourth Down Fantasy Decision Engine",description:"Free, explainable ESPN fantasy football decisions built around your real league.",type:"website"},robots:{index:true,follow:true}};

const features = [
  { icon: Cross, title: "INJURY CONTEXT", copy: "Availability changes the range, not a mystery bonus." },
  { icon: CloudRain, title: "WEATHER IMPACT", copy: "Free stadium-aware forecasts, bounded by position." },
  { icon: Activity, title: "VEGAS BASELINE", copy: "Spreads and totals establish the weekly prior." },
  { icon: BarChart3, title: "WIN PROBABILITY", copy: "Lineups judged against your actual opponent." },
];

export default function Landing() {
  const structuredData={"@context":"https://schema.org","@type":"SoftwareApplication",name:"Fourth Down",applicationCategory:"SportsApplication",operatingSystem:"Web",offers:{"@type":"Offer",price:"0",priceCurrency:"USD"},description:"A free ESPN-connected fantasy football decision engine for lineup, waiver, trade, and draft analysis."};
  return <main className="landing"><script type="application/ld+json" dangerouslySetInnerHTML={{__html:JSON.stringify(structuredData).replace(/</g,"\\u003c")}}/>
    <nav className="landing-nav"><Link className="brand" href="/"><span>4</span>TH DOWN</Link><div><Link href="/methodology">How it works</Link><Link href="/privacy">Privacy</Link><Link className="button small" href="/connect">Connect ESPN <ArrowRight size={16}/></Link></div></nav>
    <section className="hero">
      <div className="yard-lines" aria-hidden="true" />
      <div className="hero-glow left"/><div className="hero-glow right"/>
      <div className="eyebrow"><Sparkles size={14}/> FREE • EXPLAINABLE • ESPN-CONNECTED</div>
      <h1>MAKE THE CALL<br/><em>BEFORE KICKOFF.</em></h1>
      <p className="hero-copy">A Vegas-first fantasy football engine that turns your league, roster, and matchup into decisions you can actually use.</p>
      <div className="hero-actions"><Link className="button" href="/connect">Connect your league <ArrowRight size={18}/></Link><Link className="ghost" href="/dashboard">Explore the demo</Link></div>
      <div className="trust"><ShieldCheck size={16}/> Runs free in demo mode. No card. No hidden prop subscription.</div>
    </section>
    <section className="feature-band" aria-label="Engine capabilities">{features.map(({icon:Icon,title,copy})=><article key={title}><Icon/><div><h2>{title}</h2><p>{copy}</p></div></article>)}</section>
    <section className="proof"><div><span className="kicker">DECISIONS, NOT DECORATION</span><h2>Your roster has a next best move.</h2><p>Fourth Down compares legal lineups, simulates score distributions, and pairs every recommendation with its impact, uncertainty, and missing data.</p></div><div className="decision-card"><div className="card-top"><span>TOP ACTION</span><span className="live-dot">DEMO DATA</span></div><h3>Claim Josh Downs</h3><p>Drop Jaylen Waddle only if his availability falls before waivers. Otherwise preserve WR depth.</p><div className="impact"><span>Expected gain <b>+1.2 pts</b></span><span>Confidence <b>68%</b></span></div></div></section>
    <footer><span>© 2026 Fourth Down</span><span><Trophy size={15}/> Built for better Sunday decisions.</span></footer>
  </main>;
}
