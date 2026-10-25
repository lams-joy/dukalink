import { ScrollViewStyleReset } from "expo-router/html";
import type { PropsWithChildren } from "react";

export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover" />
        <title>DukaLink</title>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
        <ScrollViewStyleReset />
        <style dangerouslySetInnerHTML={{ __html: `body{background:#E3F5EE;-webkit-font-smoothing:antialiased;font-family:Inter,-apple-system,'SF Pro Display','Segoe UI',system-ui,sans-serif}` }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
