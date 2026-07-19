import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Drafts under review, and the signed-in area.
      disallow: ["/legal/", "/account"],
    },
    sitemap: "https://reenigne.dev/sitemap.xml",
  };
}
