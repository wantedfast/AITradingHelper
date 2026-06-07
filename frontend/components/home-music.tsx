"use client";

import { useEffect, useRef, useState } from "react";
import { Music2, Volume2, VolumeX } from "lucide-react";

export function HomeMusic() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [blocked, setBlocked] = useState(false);

  const play = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = 0.16;

    try {
      await audio.play();
      setPlaying(true);
      setBlocked(false);
    } catch {
      setBlocked(true);
      setPlaying(false);
    }
  };

  const pause = () => {
    audioRef.current?.pause();
    setPlaying(false);
  };

  useEffect(() => {
    void play();

    const unlock = () => {
      if (!audioRef.current?.paused) return;
      void play();
    };

    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });

    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, []);

  const label = playing ? "关闭首页音乐" : blocked ? "点击播放首页音乐" : "播放首页音乐";

  return (
    <>
      <audio ref={audioRef} src="/home-theme.mp3" loop preload="auto" />
      <button
        className={`music-toggle ${playing ? "is-playing" : ""}`}
        type="button"
        onClick={() => (playing ? pause() : void play())}
        aria-label={label}
        title={label}
      >
        <span className="music-toggle__icon">
          {playing ? <Volume2 className="h-4 w-4" /> : blocked ? <VolumeX className="h-4 w-4" /> : <Music2 className="h-4 w-4" />}
        </span>
      </button>
    </>
  );
}
