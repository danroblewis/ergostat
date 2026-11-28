import { Component, type ReactNode } from "react";

/* A part of the page that may fail on its own: a rendering error inside it is said where it was (with a button to
   draw it again) instead of taking the whole page down, so nothing around it, and nothing kept for it, is lost. */

export class Contained extends Component<{ children: ReactNode; label: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error(`${this.props.label}:`, error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="note lvl-error" role="alert">
        <p><strong>{this.props.label} failed to draw:</strong> {this.state.error.message}</p>
        <p className="small">Your work is kept. <button type="button" onClick={() => this.setState({ error: null })}>Draw it again</button></p>
      </div>
    );
  }
}
