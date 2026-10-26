import { Suspense } from "react";

import { AuthForm } from "./AuthForm";

export default function RegisterPage() {
  return <Suspense><AuthForm mode="register" /></Suspense>;
}
