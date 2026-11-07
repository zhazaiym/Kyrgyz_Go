# About page content design

## Goal

Replace the existing KyrgyzGo About content with the eight Russian story slides
provided by the user and add one fitting photograph for each slide.

## Current project structure

The repository contains the FastAPI backend, not the website frontend. Public
About data is exposed through `About` and ordered `AboutSection` records. Both
models have a title, description, image URL, active flag, and stored
translations. The existing translation worker supports Russian source content
and English, German, and Chinese translations.

## Design

- Replace existing About and AboutSection records with one About introduction
  and eight active, ordered AboutSection records, one per supplied slide.
- Preserve the user's Russian text and slide order. Use the About title for the
  overarching headline; put each slide heading and its full body into its
  corresponding section fields without adding Kyrgyz text.
- Add a distinct, relevant photograph to the `image` URL of each of the eight
  AboutSection records. Images should match each slide's subject, including
  Central Asia, local hosting, global travel, and Umrah. The backend stores image
  URLs rather than uploading files.
- Let the existing translation worker create English, German, and Chinese
  versions from the Russian source; do not create a separate translation
  pipeline.
- Keep the database schema and public endpoints unchanged. The connected
  frontend must consume `/abouts/` and `/about-sections/` for the new content.

## Data replacement and verification

Back up the current About and AboutSection rows before replacing them. Verify
the resulting row counts and order, confirm the supplied text is represented in
the Russian API responses, and check that all eight image URLs are present. Do
not change the frontend layout because its source is not included in this
checkout.

## Risks and constraints

The visual page updates only if the deployed website reads these backend
endpoints. Translation generation is asynchronous, so translated responses may
initially fall back to Russian. All eight hosted image URLs must remain
accessible to the website.
