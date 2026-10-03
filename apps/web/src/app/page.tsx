import { Hero } from "@/components/landing/hero";
import { LandingNav } from "@/components/landing/nav";
import { Bento, Compare, CtaFooter, Faq, GlassBox, LanguageStrip, MemoryStory, OneBrain, Pricing, UseCases } from "@/components/landing/sections";

export default function Home() {
  return (
    <main className="relative">
      <LandingNav />
      <Hero />
      <LanguageStrip />
      <OneBrain />
      <MemoryStory />
      <GlassBox />
      <Bento />
      <UseCases />
      <Compare />
      <Pricing />
      <Faq />
      <CtaFooter />
    </main>
  );
}
