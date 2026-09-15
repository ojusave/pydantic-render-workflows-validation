const repositoryUrl =
  "https://github.com/ojusave/pydantic-render-workflows-validation";

export const links = {
  deploy: `https://render.com/deploy?repo=${encodeURIComponent(repositoryUrl)}`,
  github: repositoryUrl,
  workflowsDocs: "https://render.com/docs/workflows",
  signup: renderSignupUrlWithUtms(),
};

export function renderSignupUrlWithUtms(
  content: string = "navbar_button",
): string {
  const params = new URLSearchParams({
    utm_source: "github",
    utm_medium: "referral",
    utm_campaign: "ojus_demos",
    utm_content: content,
  });

  return `https://dashboard.render.com/register?${params.toString()}`;
}
