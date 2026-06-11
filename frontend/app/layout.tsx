import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Merit-Trade AI — Professional AI Trading Platform",
  description: "Production-grade AI trading platform with XGBoost, LSTM, and Transformer ensemble models.",
  keywords: ["trading", "AI", "signals", "forex", "crypto", "XGBoost", "LSTM"],
  openGraph: {
    title: "Merit-Trade AI",
    description: "AI-powered trading signals with institutional-grade risk management",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
        {/* Sync localStorage token → cookie so Next.js middleware can read it */}
        <script dangerouslySetInnerHTML={{ __html: `
          (function(){
            try {
              var t = localStorage.getItem('access_token');
              if (t) document.cookie = 'access_token=' + t + '; path=/; SameSite=Lax';
              else document.cookie = 'access_token=; path=/; max-age=0';
            } catch(e) {}
          })();
        `}} />
      </head>
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  );
}
