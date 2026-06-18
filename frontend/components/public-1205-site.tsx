"use client";

import { Button, Input, Textarea } from "@heroui/react";
import { Facebook, Instagram, Mail } from "lucide-react";
import { FormEvent, useState } from "react";
import { BrandLogo } from "@/components/brand-logo";
import { submitAccessRequest } from "@/services/requests";

const navItems = [
  { label: "Home", href: "#home" },
  { label: "The Building", href: "#building" },
  { label: "Gallery", href: "#gallery" },
  { label: "Amenities", href: "#amenities" },
  { label: "Contact", href: "#contact" }
];

function splitName(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) {
    return { firstName: parts[0] || "Rental", lastName: "Inquiry" };
  }
  return { firstName: parts.slice(0, -1).join(" "), lastName: parts[parts.length - 1] };
}

export function Public1205Site() {
  const [submittedId, setSubmittedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "").trim();
    const email = String(form.get("email") || "").trim();
    const message = String(form.get("message") || "").trim();
    const { firstName, lastName } = splitName(name);

    try {
      const result = await submitAccessRequest({
        request_type: "new_access",
        requested_for_first_name: firstName,
        requested_for_last_name: lastName,
        requested_for_email: email,
        requested_for_company_text: "1205 on Franklin rental inquiry",
        requested_for_suite_text: null,
        requested_for_department: "Rental inquiry",
        reason: message || "Rental inquiry submitted from the 1205 on Franklin website.",
        requester_name: name || "Rental Inquiry",
        requester_email: email
      });
      setSubmittedId(result.request.id);
      event.currentTarget.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send inquiry");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="public-site-shell">
      <header className="public-header">
        <div className="public-header-inner">
          <BrandLogo href="#home" size="public" />
          <nav className="public-nav" aria-label="Primary navigation">
            {navItems.map((item) => (
              <a key={item.href} href={item.href}>
                {item.label}
              </a>
            ))}
          </nav>
        </div>
      </header>

      <main id="home" className="public-hero">
        <div className="public-hero-image" />
        <section className="public-hero-panel" aria-labelledby="rental-inquiries-heading">
          <div className="public-hero-copy">
            <p className="public-kicker">1205 on Franklin</p>
            <h1>Private Office Suites in Downtown Tampa</h1>
            <p>Historic character. Professional presence. Flexible office space.</p>
            <a className="public-cta" href="#contact">
              Rental Inquiries
            </a>
          </div>

          <div id="contact" className="public-inquiry-panel">
            <div className="public-inquiry-heading">
              <h2 id="rental-inquiries-heading">Rental Inquiries</h2>
              <span />
            </div>
            <div className="public-inquiry-grid">
              <div className="public-contact-details">
                <p>
                  1205 N Franklin Street
                  <br />
                  Tampa, FL 33602
                </p>
                <p>
                  <strong>Leasing Office Hours:</strong>
                  <br />
                  Mon - Fri: 7am - 10pm
                </p>
              </div>
              <form className="public-contact-form" onSubmit={submit}>
                <Input name="name" aria-label="Name" placeholder="Name" variant="flat" isRequired />
                <Input name="email" aria-label="Email" type="email" placeholder="Email" variant="flat" isRequired />
                <Textarea name="message" aria-label="Message" placeholder="Add a message" minRows={4} variant="flat" />
                {submittedId ? <p className="public-form-success">Inquiry received. Reference #{submittedId}.</p> : null}
                {error ? <p className="public-form-error">{error}</p> : null}
                <Button type="submit" variant="bordered" isLoading={loading} startContent={<Mail size={16} />}>
                  Submit
                </Button>
              </form>
            </div>
          </div>
        </section>

        <section id="building" className="public-anchor-section" aria-label="The Building" />
        <section id="gallery" className="public-anchor-section" aria-label="Gallery" />
        <section id="amenities" className="public-anchor-section" aria-label="Amenities" />
      </main>

      <footer className="public-footer">
        <div className="public-socials" aria-label="Social links">
          <span><Facebook size={18} /></span>
          <span><Instagram size={18} /></span>
        </div>
        <p>© 1205 on Franklin</p>
      </footer>
    </div>
  );
}
