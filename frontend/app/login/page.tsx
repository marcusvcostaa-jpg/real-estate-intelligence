import type { Metadata } from "next";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Entrar · Real Estate Intelligence" };

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-xl font-semibold tracking-tight">Real Estate Intelligence</h1>
        <p className="mt-1 text-sm text-zinc-500">Acesso restrito a usuários cadastrados.</p>
        <LoginForm />
      </div>
    </main>
  );
}
