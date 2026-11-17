//! `opendash-telemetry/1`: the ECU stream as JSON lines.
//!
//! The protocol is opendash's (`docs/telemetry.md` in that repository): one
//! JSON object per line. The board is the client: it reads samples
//! (`{"t":..,"n":..,"id":"0x000D","u":"km/h","v":38}`), the row list and the
//! state, and sends a selection back. This module only reads and writes text:
//! a minimal scanner for flat JSON objects, borrowing from the line, and a
//! writer for the commands, both without allocation.

use core::fmt::{self, Write};

/// A value in a flat object. Strings are returned raw (still escaped) because
/// the fields the board uses (`id`, `type`) never contain escapes.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Value<'a> {
    Str(&'a str),
    Num(f64),
    Bool(bool),
    Null,
    /// An array or object: skipped, its raw text kept.
    Nested(&'a str),
}

/// Iterate the top-level `key: value` pairs of one JSON object.
pub struct Fields<'a> {
    s: &'a str,
    i: usize,
    done: bool,
}

pub fn fields(line: &str) -> Option<Fields<'_>> {
    let t = line.trim();
    if !t.starts_with('{') || !t.ends_with('}') {
        return None;
    }
    Some(Fields { s: t, i: 1, done: false })
}

impl<'a> Fields<'a> {
    fn ws(&mut self) {
        let b = self.s.as_bytes();
        while self.i < b.len() && (b[self.i] as char).is_ascii_whitespace() {
            self.i += 1;
        }
    }

    fn string(&mut self) -> Option<&'a str> {
        let b = self.s.as_bytes();
        if b.get(self.i) != Some(&b'"') {
            return None;
        }
        let start = self.i + 1;
        let mut j = start;
        while j < b.len() {
            match b[j] {
                b'\\' => j += 2,
                b'"' => {
                    self.i = j + 1;
                    return Some(&self.s[start..j]);
                }
                _ => j += 1,
            }
        }
        None
    }

    fn nested(&mut self) -> Option<&'a str> {
        let b = self.s.as_bytes();
        let start = self.i;
        let mut depth = 0i32;
        let mut j = self.i;
        while j < b.len() {
            match b[j] {
                b'"' => {
                    j += 1;
                    while j < b.len() && b[j] != b'"' {
                        if b[j] == b'\\' {
                            j += 1;
                        }
                        j += 1;
                    }
                }
                b'[' | b'{' => depth += 1,
                b']' | b'}' => {
                    depth -= 1;
                    if depth == 0 {
                        self.i = j + 1;
                        return Some(&self.s[start..=j]);
                    }
                }
                _ => {}
            }
            j += 1;
        }
        None
    }

    fn value(&mut self) -> Option<Value<'a>> {
        self.ws();
        let b = self.s.as_bytes();
        match *b.get(self.i)? {
            b'"' => self.string().map(Value::Str),
            b'[' | b'{' => self.nested().map(Value::Nested),
            b't' if self.s[self.i..].starts_with("true") => {
                self.i += 4;
                Some(Value::Bool(true))
            }
            b'f' if self.s[self.i..].starts_with("false") => {
                self.i += 5;
                Some(Value::Bool(false))
            }
            b'n' if self.s[self.i..].starts_with("null") => {
                self.i += 4;
                Some(Value::Null)
            }
            _ => {
                let start = self.i;
                while self.i < b.len() && matches!(b[self.i], b'0'..=b'9' | b'-' | b'+' | b'.' | b'e' | b'E') {
                    self.i += 1;
                }
                self.s[start..self.i].parse::<f64>().ok().map(Value::Num)
            }
        }
    }
}

impl<'a> Iterator for Fields<'a> {
    type Item = (&'a str, Value<'a>);

    fn next(&mut self) -> Option<Self::Item> {
        if self.done {
            return None;
        }
        self.ws();
        let b = self.s.as_bytes();
        if b.get(self.i) == Some(&b'}') {
            self.done = true;
            return None;
        }
        let key = self.string()?;
        self.ws();
        if b.get(self.i) != Some(&b':') {
            self.done = true;
            return None;
        }
        self.i += 1;
        let v = self.value();
        self.ws();
        match b.get(self.i) {
            Some(b',') => self.i += 1,
            Some(b'}') => {}
            _ => self.done = true,
        }
        match v {
            Some(v) => Some((key, v)),
            None => {
                self.done = true;
                None
            }
        }
    }
}

/// One value from the stream.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Sample<'a> {
    /// Sender's clock, ms since 1970.
    pub t: i64,
    pub id: &'a str,
    pub unit: &'a str,
    /// `None` when the sender had no number (`null`).
    pub v: Option<f64>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Line<'a> {
    Sample(Sample<'a>),
    Hello,
    /// The row list; the raw array is kept for whoever wants to show it.
    Rows(&'a str),
    State { running: bool, rounds: u32 },
    Ack { ok: bool },
    Other,
}

pub fn parse(line: &str) -> Option<Line<'_>> {
    let mut ty = None;
    let (mut t, mut id, mut unit, mut v, mut seen_v) = (None, None, "", None, false);
    let (mut rows, mut running, mut rounds, mut ok) = (None, false, 0u32, false);
    for (k, val) in fields(line)? {
        match (k, val) {
            ("type", Value::Str(s)) => ty = Some(s),
            ("t", Value::Num(x)) => t = Some(x as i64),
            ("id", Value::Str(s)) => id = Some(s),
            ("u", Value::Str(s)) => unit = s,
            ("v", Value::Num(x)) => {
                v = Some(x);
                seen_v = true
            }
            ("v", Value::Null) => seen_v = true,
            ("rows", Value::Nested(s)) => rows = Some(s),
            ("running", Value::Bool(b)) => running = b,
            ("rounds", Value::Num(x)) => rounds = x as u32,
            ("ok", Value::Bool(b)) => ok = b,
            _ => {}
        }
    }
    Some(match ty {
        None => match (t, id, seen_v) {
            (Some(t), Some(id), true) => Line::Sample(Sample { t, id, unit, v }),
            _ => Line::Other,
        },
        Some("hello") => Line::Hello,
        Some("rows") => Line::Rows(rows.unwrap_or("[]")),
        Some("state") => Line::State { running, rounds },
        Some("ack") => Line::Ack { ok },
        Some(_) => Line::Other,
    })
}

fn list(out: &mut impl Write, items: &[&str]) -> fmt::Result {
    out.write_char('[')?;
    for (k, s) in items.iter().enumerate() {
        if k > 0 {
            out.write_char(',')?;
        }
        out.write_char('"')?;
        for c in s.chars() {
            match c {
                '"' => out.write_str("\\\"")?,
                '\\' => out.write_str("\\\\")?,
                c if (c as u32) < 0x20 => write!(out, "\\u{:04x}", c as u32)?,
                c => out.write_char(c)?,
            }
        }
        out.write_char('"')?;
    }
    out.write_char(']')
}

/// `{"select":[..],"always":[..],"start":true}` plus the newline.
pub fn write_select(out: &mut impl Write, rows: &[&str], always: &[&str], start: bool) -> fmt::Result {
    out.write_str("{\"select\":")?;
    list(out, rows)?;
    if !always.is_empty() {
        out.write_str(",\"always\":")?;
        list(out, always)?;
    }
    if start {
        out.write_str(",\"start\":true")?;
    }
    out.write_str("}\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sample_from_opendash() {
        let l = r#"{"t":1763390000123,"n":"Engine \"Speed\"","id":"0x000C","u":"RPM","v":812.5}"#;
        assert_eq!(
            parse(l),
            Some(Line::Sample(Sample { t: 1763390000123, id: "0x000C", unit: "RPM", v: Some(812.5) }))
        );
        let l = r#"{"t":1,"n":"x","id":"PID 0D","u":"km/h","v":null}"#;
        assert_eq!(parse(l), Some(Line::Sample(Sample { t: 1, id: "PID 0D", unit: "km/h", v: None })));
    }

    #[test]
    fn control_lines() {
        assert_eq!(parse(r#"{"type":"hello","proto":"opendash-telemetry/1"}"#), Some(Line::Hello));
        assert_eq!(
            parse(r#"{"type":"state","running":true,"rounds":2,"keys":["cat:a|1|1|X(0)|"]}"#),
            Some(Line::State { running: true, rounds: 2 })
        );
        assert_eq!(parse(r#"{"type":"ack","ok":false,"why":"no"}"#), Some(Line::Ack { ok: false }));
        match parse(r#"{"type":"rows","module":"E","rows":[{"key":"k","name":"a]b","id":"0x0001","unit":""}]}"#) {
            Some(Line::Rows(r)) => assert!(r.starts_with("[{") && r.ends_with("}]")),
            other => panic!("{:?}", other),
        }
    }

    #[test]
    fn junk_is_not_a_sample() {
        assert_eq!(parse("not json"), None);
        assert_eq!(parse(r#"{"t":1,"id":"0x1"}"#), Some(Line::Other));
        assert_eq!(parse(r#"{"t":1,"id":"0x1","v":"#), None);
    }

    #[test]
    fn select_line() {
        let mut s = String::new();
        write_select(&mut s, &["0x000D", "0x000C", "a\"b"], &["0x000D"], true).unwrap();
        assert_eq!(s, "{\"select\":[\"0x000D\",\"0x000C\",\"a\\\"b\"],\"always\":[\"0x000D\"],\"start\":true}\n");
    }
}
