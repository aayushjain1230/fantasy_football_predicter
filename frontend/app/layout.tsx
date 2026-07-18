import type { Metadata } from "next";
import "./globals.css";
import { ServiceWorker } from "../components/ServiceWorker";

const siteUrl=process.env.NEXT_PUBLIC_SITE_URL||"http://localhost:3000";
export const metadata: Metadata = { metadataBase:new URL(siteUrl),title:{default:"Fourth Down | Fantasy decisions, simulated",template:"%s | Fourth Down"},description:"A free, Vegas-first ESPN fantasy football decision engine.",applicationName:"Fourth Down",category:"sports",authors:[{name:"Fourth Down"}] };
export default function Layout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}<ServiceWorker/></body></html>; }
