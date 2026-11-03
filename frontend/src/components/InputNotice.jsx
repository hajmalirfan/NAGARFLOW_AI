/** Says that what a form records is an evaluation input, not a municipal fact. */
export default function InputNotice() {
  return (
    <p className="notice">
      <strong>Evaluation inputs.</strong> Values entered here are synthetic or assumed for
      evaluation, not verified municipal records.
    </p>
  );
}
