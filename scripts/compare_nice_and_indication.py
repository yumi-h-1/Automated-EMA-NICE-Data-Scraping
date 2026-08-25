"""Ask the model whether each NICE page matches the EMA indication."""

import pandas as pd

from extractors import query_model_for_NICE_similarity


def compare_nice_and_indication(nice_text_dict, indication_df):
    """`indication_df` has two columns: the indication text and 'NICE_url'."""
    indication_column = [c for c in indication_df.columns if c != 'NICE_url'][0]
    similarity_results = []

    for url, nice_text in nice_text_dict.items():
        try:
            rows = indication_df.loc[indication_df['NICE_url'] == url, indication_column]
            if rows.empty:
                similarity_results.append(
                    {'NICE_url': url, 'Result': 'No matching indication found in DataFrame'}
                )
                continue

            # Take the indication text itself, not the whole row: passing the
            # row handed the model a numpy array repr instead of the wording.
            indication = rows.iloc[0]
            if pd.isna(indication) or str(indication).strip() in ('', 'N/A'):
                similarity_results.append({'NICE_url': url, 'Result': 'N/A'})
                continue

            similarity_results.append(
                {'NICE_url': url, 'Result': query_model_for_NICE_similarity(nice_text, str(indication))}
            )

        except Exception as e:
            print(f'Error processing comparison for {url}: {e}')
            similarity_results.append({'NICE_url': url, 'Result': 'Error'})

    return similarity_results
