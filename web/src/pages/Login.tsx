import { useLogin } from "@refinedev/core";
import { useState, type FormEvent } from "react";
import { ProofChain, type ChainLink } from "../components/ProofChain";
import { Wordmark } from "../components/Wordmark";
import "../styles/login.css";

const EXAMPLE: ChainLink[] = [
  { name: "Agreement", detail: "Accepted 28 Oct", state: "proven" },
  { name: "Invoice", detail: "INV-0042", state: "proven" },
  { name: "Payment", detail: "Paid 4 Nov", state: "proven" },
  { name: "Deliverable", detail: "Not uploaded", state: "missing" },
];

export function LoginPage() {
  const { mutate: login, isPending } = useLogin<{ email: string; password: string }>();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFailed(null);
    login(
      { email, password },
      {
        onSuccess: (data) => {
          if (!data.success) setFailed(data.error?.message ?? "That email and password don't match.");
        },
      },
    );
  };

  return (
    <div className="login">
      <section className="login-form">
        <Wordmark />
        <div>
          <h1>Sign in</h1>
          <p className="login-lede">Keep proof for every PayPal payment you receive.</p>
        </div>
        <form onSubmit={submit} noValidate={false}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              maxLength={254}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              maxLength={256}
            />
          </div>
          {failed && (
            <p className="alert" role="alert">
              {failed}
            </p>
          )}
          <button type="submit" className="button" disabled={isPending}>
            {isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>

      <section className="login-story" aria-labelledby="story-title">
        <h2 id="story-title">When PayPal asks what a payment was for, have the answer.</h2>
        <p>
          Kweli links every payment to its agreement, invoice and delivered work, and shows you
          exactly what's missing before anyone asks.
        </p>
        <figure className="receipt">
          <div className="receipt-head">
            <span className="receipt-amount">$800.00</span>
            <span className="receipt-from">from Acme Ltd</span>
          </div>
          <ProofChain links={EXAMPLE} animate />
          <figcaption className="visually-hidden">
            Example payment with three of four proofs on file. The deliverable is missing.
          </figcaption>
        </figure>
      </section>
    </div>
  );
}
