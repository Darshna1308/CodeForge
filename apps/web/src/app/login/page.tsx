import { Suspense } from "react";

import { AuthForm } from "../register/AuthForm";

export default function LoginPage() {
  return <Suspense><AuthForm mode="login" /></Suspense>;
}
