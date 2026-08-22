# Provider Request Sequence — AURA v3.5

> **Verified from:** `src/aura/providers.py`, `src/aura/llm.py`, `src/aura/remediation.py:244-579`

## Sequence: LLM Provider Request with Circuit Breaker & Fallback

```mermaid
sequenceDiagram
    participant Loop as AutonomousRemediationLoop
    participant Provider as ProviderRegistry
    participant CB as CircuitBreaker
    participant Primary as OpenAICompatibleProvider
    participant Fallback as Ollama (optional)
    participant HTTP as LLM API
    participant DB as Database
    
    Loop->>Provider: chat_with_fallback(system_prompt, user_message)
    Provider->>Provider: get_healthy_provider()
    
    Note over Provider: Check priority order
    Provider->>Primary: Check circuit state
    Primary->>CB: allow_request()
    
    alt Circuit CLOSED or HALF_OPEN
        CB-->>Primary: true
        Provider-->>Loop: Returns primary provider
        Loop->>Primary: chat(system_prompt, user_message)
        Primary->>CB: _wrap_call(fn)
        Primary->>HTTP: POST /chat/completions
        
        alt HTTP 200
            HTTP-->>Primary: JSON: choices[0].message.content
            Primary->>CB: record_success()
            Primary-->>Loop: ProviderResponse(content, model, tokens, untrusted=True)
        else HTTP 429 (rate limited)
            Primary->>Primary: Retry with exponential backoff (max 3)
            Primary->>HTTP: POST /chat/completions (retry)
            
            alt Successful retry
                HTTP-->>Primary: JSON: choices[0].message.content
                Primary->>CB: record_success()
                Primary-->>Loop: ProviderResponse(content, ...)
            else All retries exhausted
                Primary->>CB: record_failure()
                Primary-->>Loop: ProviderResponse(error="Rate limited", ...)
            end
        else HTTP != 200
            HTTP-->>Primary: Error response
            Primary->>CB: record_failure()
            Primary-->>Loop: ProviderResponse(error="HTTP NNN: ...", ...)
        end
        
    else Circuit OPEN
        CB-->>Primary: false
        Provider->>Fallback: Check circuit state
        Fallback->>CB: allow_request()
        
        alt Fallback available
            Provider-->>Loop: Returns fallback provider
            Note over Loop,Fallback: Same chat flow with fallback
        else No healthy provider
            Provider-->>Loop: ProviderResponse(error="All providers unhealthy")
        end
    end
    
    alt Response has error
        Loop->>DB: insert_dead_letter(finding_id, cycle, error_type='PROVIDER_ERROR')
    else Response OK but untrusted
        Loop->>Loop: Parse JSON from LLM response
    end
```

## Sequence: Autonomous Fix → Verify → Re-audit

```mermaid
sequenceDiagram
    participant Loop as AutonomousRemediationLoop
    participant Engine as Engine
    participant LLM as LLM (via ProviderRegistry)
    participant Fixer as AutoFixer
    participant FS as Filesystem
    participant Tools as Tooling
    participant DB as Database
    participant Judge as ConvergenceJudge
    
    loop Until convergence or max cycles
        Loop->>Engine: run_audit()
        Engine-->>Loop: audit_result
        
        alt PRODUCTION_READY
            Loop->>Judge: evaluate(current, previous_states)
            Judge-->>Loop: ConvergenceResult(converged=True/False)
            
            alt Judge confirms convergence
                Loop-->>Loop: return "converged"
            end
        end
        
        Loop->>Loop: safeguard.can_continue(score, findings)
        alt Cannot continue
            Loop-->>Loop: return "safeguard_stop"
        end
        
        Loop->>DB: get_findings()
        DB-->>Loop: findings list
        
        loop Fixable findings (max 20/cycle)
            Loop->>LLM: chat("Autonomous Fixer", fix_prompt)
            LLM-->>Loop: JSON fix data
            
            alt Parse successful
                Loop->>Fixer: apply_fix(file, line_start, line_end, old_code, new_code)
                Fixer->>Fixer: Sandbox checks (path traversal, dangerous patterns)
                
                alt Sandbox passes
                    Fixer->>FS: read_file() → backup content
                    Fixer->>Fixer: Verify old_code matches
                    Fixer->>FS: write_file() → new content
                    Fixer-->>Loop: FixResult(success=True, diff)
                    Loop->>DB: insert_remediation_attempt(APPLIED)
                    Loop->>DB: update_finding_status(FIXED)
                else Sandbox rejected or old_code mismatch
                    Fixer-->>Loop: FixResult(success=False, error)
                    Loop->>LLM: Retry with actual file content
                    LLM-->>Loop: Corrected fix data
                    Note over Loop,FS: Second attempt (same sandbox flow)
                end
            else Parse failed
                Loop->>DB: insert_dead_letter(UNPARSEABLE)
            end
        end
        
        alt Fixes applied
            Loop->>Tools: subprocess.run(test commands)
            Tools-->>Loop: exit codes
            
            alt Tooling failed
                Loop->>Fixer: rollback() — restore backups
                Fixer-->>Loop: rollback summary
            else Tooling passed
                Loop->>Loop: Save cycle evidence
            end
        end
    end
```