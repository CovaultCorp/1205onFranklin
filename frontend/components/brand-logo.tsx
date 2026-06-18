import Link from "next/link";
import Image from "next/image";

type BrandLogoProps = {
  href?: string;
  size?: "sidebar" | "auth" | "compact" | "public";
};

export function BrandLogo({ href = "/dashboard", size = "sidebar" }: BrandLogoProps) {
  const logo = (
    <span className={`brand-logo-shell brand-logo-${size}`}>
      <Image
        src="/images/1205-logo.png"
        alt="1205 on Franklin"
        width={1536}
        height={1024}
        className="brand-logo-image"
        priority={size !== "compact"}
      />
    </span>
  );

  if (!href) {
    return logo;
  }

  return (
    <Link href={href} aria-label="1205 on Franklin home">
      {logo}
    </Link>
  );
}
