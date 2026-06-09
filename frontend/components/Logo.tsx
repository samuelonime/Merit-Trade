"use client";

import Image from "next/image";
import Link from "next/link";

interface LogoProps {
  href?: string;
  size?: number;
  showText?: boolean;
  className?: string;
  alt?: string;
}

export default function Logo({
  href = "/",
  size = 40,
  showText = true,
  className = "",
  alt = "MeritTrade AI logo",
}: LogoProps) {
  return (
    <Link href={href} className={`logo ${className}`.trim()}>
      <Image
        src="/merit.svg"
        alt={alt}
        width={size}
        height={size}
        priority
      />
      {showText ? (
        <span className="logo-text">
          Merit<span>Trade</span> AI
        </span>
      ) : null}
      <style jsx>{`
        .logo {
          display: inline-flex;
          align-items: center;
          gap: 0.75rem;
          text-decoration: none;
          color: inherit;
        }
        .logo-text {
          font-weight: 700;
          letter-spacing: 0.01em;
          font-size: 1rem;
        }
        .logo-text span {
          color: #00d4ff;
        }
      `}</style>
    </Link>
  );
}
