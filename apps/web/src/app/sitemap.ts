import type { MetadataRoute } from "next";

const BASE = "https://reenigne.dev";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${BASE}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE}/sample-report`, lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    { url: `${BASE}/pricing`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${BASE}/download`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
    { url: `${BASE}/docs`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${BASE}/feedback`, lastModified: now, changeFrequency: "yearly", priority: 0.4 },
  ];
}
