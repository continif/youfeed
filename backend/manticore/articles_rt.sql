-- Manticore RT index `articles_rt` per YOUFEED.
-- Applicare con:
--   mysql -h 127.0.0.1 -P 9306 < backend/manticore/articles_rt.sql
--
-- Schema: vedi Claude/DATABASE.md -> "Schema Manticore"
-- Morphology: libstemmer_it (lemmatize_it_all non disponibile)
-- Wordforms + stopwords: caricati via /etc/manticoresearch/manticore.conf
--
-- NB: Manticore non accetta IF NOT EXISTS in CREATE TABLE; per re-applicare
-- usa prima: DROP TABLE articles_rt;

CREATE TABLE articles_rt (
    title text,
    description text,
    content_text text,
    content_html text stored,
    source_id bigint,
    source_domain string,
    topic_ids multi64,
    topic_slugs_csv string,
    published_at timestamp,
    kind string
) morphology='libstemmer_it' min_word_len='2' expand_keywords='1' index_exact_words='1';
