import type { NextConfig } from "next";
const securityHeaders=[
 {key:"X-Content-Type-Options",value:"nosniff"},{key:"X-Frame-Options",value:"DENY"},{key:"Referrer-Policy",value:"no-referrer"},
 {key:"Permissions-Policy",value:"camera=(), microphone=(), geolocation=()"},
 {key:"Content-Security-Policy",value:"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' http://localhost:8000 http://127.0.0.1:8000; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"}
];
const privateRoutes=["/connect","/dashboard","/lineup","/waivers","/trades","/draft","/players/:path*","/what-if","/power-rankings","/standings-projection","/reports","/trust","/data-sources","/settings"];
const config: NextConfig = { reactStrictMode: true, poweredByHeader:false, async headers(){return [{source:"/(.*)",headers:securityHeaders},...privateRoutes.map(source=>({source,headers:[{key:"X-Robots-Tag",value:"noindex, nofollow, noarchive"}]}))]}};
export default config;
