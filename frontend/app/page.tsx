"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";

const heroStream = "/hero-original.mp4";
const heroPoster =
  "https://image.mux.com/Aa02T7oM1wH5Mk5EEVDYhbZ1ChcdhRsS2m1NYyx4Ua1g/thumbnail.jpg?time=1";

const projectImages = [
  "https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=1600&q=80",
  "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1600&q=80",
  "https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?auto=format&fit=crop&w=1600&q=80",
  "https://images.unsplash.com/photo-1642104704074-907c0698cbd9?auto=format&fit=crop&w=1600&q=80",
];

const modules = [
  {
    title: "研究",
    subtitle: "把信息变成判断",
    description: "识别市场情绪、板块方向与个股强弱，让注意力停留在真正影响决策的变量上。",
  },
  {
    title: "预案",
    subtitle: "先定义，再执行",
    description: "在交易发生前写清条件、边界与动作，避免盘中情绪替代计划。",
  },
  {
    title: "盯盘",
    subtitle: "只提醒真正重要的信号",
    description: "围绕你的交易预案监控盘中变化，在关键触发出现时再提醒你行动。",
  },
  {
    title: "复盘",
    subtitle: "让每一笔交易留下结论",
    description: "从交割记录还原执行过程，看清问题、总结边界，并沉淀到下一次交易里。",
  },
];

const workflow = [
  ["研究环境与逻辑", "先看明白市场在发生什么", "May 12, 2026"],
  ["定义预案与边界", "把进场、离场与风险写清楚", "Apr 28, 2026"],
  ["盘中盯盘与提醒", "只在关键触发出现时提醒你", "Mar 18, 2026"],
  ["复盘与更新规则", "把一次交易变成可复用认知", "Feb 06, 2026"],
];

declare global {
  interface Window {
    Hls?: {
      Events?: {
        MANIFEST_PARSED: string;
      };
      isSupported: () => boolean;
      new (): {
        loadSource: (src: string) => void;
        attachMedia: (media: HTMLMediaElement) => void;
        destroy: () => void;
        on?: (event: string, callback: () => void) => void;
        levels?: unknown[];
        currentLevel?: number;
        nextLevel?: number;
        loadLevel?: number;
      };
    };
  }
}

function useHeroVideo(videoRef: RefObject<HTMLVideoElement | null>) {
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let canceled = false;
    let detachLoad: (() => void) | null = null;
    let hlsInstance: { destroy: () => void } | null = null;

    const attachStream = () => {
      if (canceled || !video) return;

      if (heroStream.endsWith(".mp4")) {
        video.src = heroStream;
        return;
      }

      if (window.Hls?.isSupported()) {
        const hls = new window.Hls();
        hls.on?.(window.Hls.Events?.MANIFEST_PARSED ?? "hlsManifestParsed", () => {
          const topLevel = (hls.levels?.length ?? 1) - 1;
          if (topLevel >= 0) {
            hls.currentLevel = topLevel;
            hls.nextLevel = topLevel;
            hls.loadLevel = topLevel;
          }
        });
        hls.loadSource(heroStream);
        hls.attachMedia(video);
        hlsInstance = hls;
        return;
      }

      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = heroStream;
      }
    };

    if (window.Hls || heroStream.endsWith(".mp4")) {
      attachStream();
    } else {
      const existing = document.querySelector<HTMLScriptElement>('script[data-hls-cdn="true"]');
      const onLoad = () => attachStream();
      detachLoad = () => existing?.removeEventListener("load", onLoad);

      if (existing) {
        existing.addEventListener("load", onLoad, { once: true });
      } else {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js";
        script.async = true;
        script.dataset.hlsCdn = "true";
        script.addEventListener("load", onLoad, { once: true });
        document.body.appendChild(script);
        detachLoad = () => script.removeEventListener("load", onLoad);
      }
    }

    return () => {
      canceled = true;
      detachLoad?.();
      hlsInstance?.destroy();
    };
  }, [videoRef]);
}

function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const links = [
    { label: "功能", href: "#modules" },
    { label: "AI 复盘", href: "/review" },
    { label: "AI 盯盘", href: "/watch" },
  ];

  return (
    <nav className="fixed inset-x-0 top-0 z-50 px-6 pt-5 md:px-8 md:pt-7">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-6">
        <Link href="/" className="group inline-flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-full border border-white/18 bg-black/32 p-[2px] backdrop-blur-xl transition-transform group-hover:scale-105">
            <span className="grid h-full w-full place-items-center overflow-hidden rounded-full bg-black/55">
              <Image src="/brand-logo.png" alt="盈航 logo" width={26} height={26} className="h-6 w-6 rounded-full object-cover" />
            </span>
          </span>
          <span className="hero-nav-brand text-white/96">盈航</span>
        </Link>

        <div
          className={`hidden items-center gap-6 rounded-full border px-5 py-3 text-sm backdrop-blur-xl transition-all md:flex ${
            scrolled
              ? "border-white/12 bg-black/18 text-white/76"
              : "border-white/10 bg-black/10 text-white/70"
          }`}
        >
          {links.map((link) =>
            link.href.startsWith("/") ? (
              <Link key={link.label} href={link.href} className="transition-colors hover:text-white">
                {link.label}
              </Link>
            ) : (
              <a key={link.label} href={link.href} className="transition-colors hover:text-white">
                {link.label}
              </a>
            ),
          )}
          <Link href="/review" className="inline-flex items-center gap-1 text-white/92 transition-colors hover:text-white">
            开始 <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </nav>
  );
}

function Hero() {
  const videoRef = useRef<HTMLVideoElement>(null);
  useHeroVideo(videoRef);

  return (
    <section
      id="home"
      className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-24 text-center md:px-8"
    >
      <video
        ref={videoRef}
        className="hero-stream absolute inset-0 h-full w-full object-cover object-center"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        poster={heroPoster}
      />
      <div className="absolute inset-0 bg-black/10" />
      <div className="absolute inset-x-0 top-0 h-[28vh] bg-gradient-to-b from-[#8ec8ff1a] via-black/6 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-[34vh] bg-gradient-to-t from-black via-black/50 to-transparent" />

      <div className="relative z-10 mx-auto mt-[16vh] flex max-w-[1100px] flex-col items-center">
        <h1 className="hero-slogan-editorial whitespace-nowrap text-[clamp(2.6rem,6.2vw,6.6rem)] leading-[0.92]">
          带你读懂市场涨跌
        </h1>
        <div className="mt-10 inline-flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/review"
            className="hero-button-primary inline-flex items-center gap-2 rounded-full px-8 py-4 text-sm font-semibold transition-transform hover:scale-[1.02]"
          >
            现在开始
          </Link>
          <a
            href="#workflow"
            className="hero-button-secondary inline-flex items-center gap-2 rounded-full px-8 py-4 text-sm font-semibold transition-transform hover:scale-[1.02]"
          >
            观看教学视频
          </a>
        </div>
      </div>
    </section>
  );
}

function SectionHeader({
  eyebrow,
  title,
  italic,
  subtext,
  cta,
}: {
  eyebrow: string;
  title: string;
  italic: string;
  subtext: string;
  cta: string;
}) {
  return (
    <div className="mb-10 flex items-end justify-between gap-8 md:mb-14">
      <div>
        <div className="mb-5 flex items-center gap-4">
          <span className="h-px w-8 bg-stroke" />
          <span className="text-xs uppercase tracking-[0.3em] text-muted">{eyebrow}</span>
        </div>
        <h2 className="text-balance text-4xl font-medium tracking-tight md:text-6xl">
          {title} <span className="font-display italic">{italic}</span>
        </h2>
        <p className="mt-4 max-w-xl text-pretty text-sm leading-7 text-muted md:text-base">{subtext}</p>
      </div>
      <a href="#footer-cta" className="group relative hidden rounded-full p-[2px] md:inline-flex">
        <span className="absolute inset-0 rounded-full opacity-0 transition-opacity group-hover:opacity-100 animated-gradient-border" />
        <span className="relative inline-flex items-center gap-2 rounded-full bg-bg px-5 py-3 text-sm text-text-primary">
          {cta} <ArrowRight size={15} />
        </span>
      </a>
    </div>
  );
}

function Modules() {
  const spans = ["md:col-span-7", "md:col-span-5", "md:col-span-5", "md:col-span-7"];
  const ratios = ["aspect-[1.25]", "aspect-[0.92]", "aspect-[0.92]", "aspect-[1.25]"];

  return (
    <section id="modules" className="bg-bg py-12 md:py-16">
      <div className="mx-auto max-w-[1200px] px-6 md:px-10 lg:px-16">
        <SectionHeader
          eyebrow="Core Modules"
          title="向下展开的是"
          italic="交易系统"
          subtext="不是一组零散功能，而是从研究、预案到盯盘、复盘和消息提醒的整套决策流程。"
          cta="开始使用"
        />
        <div className="grid grid-cols-1 gap-5 md:grid-cols-12 md:gap-6">
          {modules.map((module, index) => (
            <article
              key={module.title}
              className={`${spans[index]} ${ratios[index]} group relative overflow-hidden rounded-3xl border border-stroke bg-surface`}
            >
              <img
                src={projectImages[index]}
                alt=""
                className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/55 to-black/15" />
              <div className="halftone absolute inset-0 opacity-20 mix-blend-multiply" />
              <div className="absolute inset-x-0 bottom-0 p-6 md:p-8">
                <p className="text-xs uppercase tracking-[0.24em] text-white/60">{module.subtitle}</p>
                <h3 className="mt-3 text-4xl font-semibold tracking-tight text-white md:text-5xl">{module.title}</h3>
                <p className="mt-4 max-w-md text-sm leading-7 text-white/78 md:text-base">{module.description}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Workflow() {
  return (
    <section id="workflow" className="bg-bg py-16 md:py-24">
      <div className="mx-auto max-w-[1200px] px-6 md:px-10 lg:px-16">
        <SectionHeader
          eyebrow="Decision Loop"
          title="交易不是一次"
          italic="反应"
          subtext="真正有价值的页面，不是解释 AI 会做什么，而是让用户看见自己如何把判断变成流程。"
          cta="进入 AI 复盘"
        />
        <div className="space-y-4">
          {workflow.map(([title, detail, date]) => (
            <a
              key={title}
              href="#footer-cta"
              className="group flex items-center gap-5 rounded-[40px] border border-stroke bg-surface/30 p-4 transition-colors hover:bg-surface sm:rounded-full"
            >
              <div className="grid h-16 w-16 shrink-0 place-items-center rounded-full border border-white/10 bg-bg text-lg font-display italic text-text-primary">
                盈航
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-base font-medium text-text-primary md:text-xl">{title}</h3>
                <p className="mt-1 text-xs text-muted md:text-sm">
                  {date} <span className="px-2 text-stroke">/</span> {detail}
                </p>
              </div>
              <ArrowRight
                className="mr-2 shrink-0 text-muted transition-transform group-hover:translate-x-1 group-hover:text-text-primary"
                size={18}
              />
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

function FooterCta() {
  return (
    <footer id="footer-cta" className="relative overflow-hidden bg-bg pb-10 pt-16 md:pb-12 md:pt-20">
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat opacity-30"
        style={{ backgroundImage: `url(${heroPoster})` }}
      />
      <div className="absolute inset-0 bg-black/68" />
      <div className="relative z-10">
        <div className="mb-14 overflow-hidden whitespace-nowrap border-y border-white/10 py-6">
          <div className="inline-flex">
            {Array.from({ length: 12 }).map((_, index) => (
              <span key={index} className="pr-8 font-display text-5xl italic text-text-primary/80 md:text-8xl">
                INVEST WITH CONTEXT *
              </span>
            ))}
          </div>
        </div>

        <div className="mx-auto max-w-[1100px] px-6 text-center md:px-10">
          <h2 className="mx-auto max-w-3xl text-balance text-5xl font-medium tracking-tight md:text-7xl">
            先判断，再让 <span className="font-display italic">盈航</span> 提醒你行动。
          </h2>
          <Link href="/review" className="group relative mt-10 inline-flex rounded-full p-[2px]">
            <span className="absolute inset-0 rounded-full opacity-0 transition-opacity group-hover:opacity-100 animated-gradient-border" />
            <span className="relative rounded-full bg-text-primary px-7 py-3.5 text-sm font-semibold text-bg">
              上传交割单开始复盘
            </span>
          </Link>
        </div>

        <div className="mx-auto mt-16 flex max-w-[1100px] flex-col items-center justify-between gap-5 border-t border-white/10 px-6 pt-6 text-sm text-muted md:flex-row md:px-10">
          <div className="flex flex-wrap justify-center gap-5">
            <Link href="/review" className="transition-colors hover:text-text-primary">
              AI 复盘
            </Link>
            <Link href="/watch" className="transition-colors hover:text-text-primary">
              AI 盯盘
            </Link>
            <a href="#modules" className="transition-colors hover:text-text-primary">
              功能
            </a>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            持续优化你的交易决策
          </div>
        </div>
      </div>
    </footer>
  );
}

export default function Page() {
  return (
    <main className="bg-bg text-text-primary">
      <Nav />
      <Hero />
      <Modules />
      <Workflow />
      <FooterCta />
    </main>
  );
}
