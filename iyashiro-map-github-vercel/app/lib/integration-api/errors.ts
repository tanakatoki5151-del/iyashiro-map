export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function errorResponse(error: unknown): Response {
  if (error instanceof ApiError) {
    return Response.json(
      { error: error.code, message: error.message, details: error.details ?? null },
      { status: error.status },
    );
  }
  console.error("integration_api_unhandled", error);
  return Response.json(
    {
      error: "internal_error",
      message: "処理に失敗しました。入力を確認して再試行してください。",
    },
    { status: 500 },
  );
}
