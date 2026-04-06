# 📚 Publishing Guide - HomGar/RainPoint Cloud Integration

> **🔒 INTERNAL DOCUMENTATION**  
> This guide contains internal development processes and should not be shared publicly.  
> Already included in .gitignore to prevent accidental commits.

This guide contains all the important steps and checklists for publishing changes to the GitHub repository.

---

## 🚀 Release Process Checklist

### **📋 Pre-Release Checklist**

#### **Code Quality**
- [ ] Test all new features thoroughly
- [ ] Update documentation for any UI/UX changes
- [ ] Check for any hardcoded values that should be configurable
- [ ] Verify backward compatibility for existing users
- [ ] Test with both HomGar and RainPoint app types

#### **Documentation Updates**
- [ ] Update README.md with new features
- [ ] Update device compatibility table if new models added
- [ ] Add/update troubleshooting sections for new issues
- [ ] Check all app references are interchangeable (HomGar/RainPoint)
- [ ] Verify API login conflict warnings are present

#### **Translation Support**
- [ ] Update `strings.json` for any new form fields
- [ ] Use proper translation keys instead of hardcoded text
- [ ] Ensure app type options are clean ("HomGar", "RainPoint")
- [ ] Add user-friendly descriptions for setup steps

#### **Version Management**
- [ ] Bump version in `custom_components/homgar/manifest.json`
- [ ] Follow semantic versioning (MAJOR.MINOR.PATCH)
  - **MAJOR**: Breaking changes
  - **MINOR**: New features (backward compatible)
  - **PATCH**: Bug fixes and improvements

---

## 🏷️ Git Commands for Release

### **Step 1: Check Status**
```bash
git status
```

### **Step 2: Add All Changes**
```bash
git add .
```

### **Step 3: Commit Changes**
```bash
# For major/minor releases:
git commit -m "feat: v{VERSION} - {Brief description}

Major features:
- {Feature 1}
- {Feature 2}
- {Feature 3}

Technical improvements:
- {Technical improvement 1}
- {Technical improvement 2}

Breaking changes:
- {Any breaking changes or 'None - seamless upgrade'}"

# For patch releases:
git commit -m "fix: v{VERSION} - {Brief description}

Fixed:
- {Bug fix 1}
- {Bug fix 2}

Improved:
- {Improvement 1}
- {Improvement 2}"
```

### **Step 4: Create Tag**
```bash
git tag -a v{VERSION} -m "v{VERSION} - {Brief description}

{Extended description of release}
{Key features in bullet points}
{Any important notes for users}"
```

### **Step 5: Push to Remote**
```bash
git push origin main
git push origin v{VERSION}
```

---

## 📝 Release Message Templates

### **Major/Minor Release Template**
```
v{VERSION} - {Brief description}

Major release with {key benefit} for Home Assistant users.

Key Features:
• {Feature 1}
• {Feature 2}
• {Feature 3}

• Backward compatible upgrade path
• Complete documentation and troubleshooting guides
• API login conflict solutions included

Perfect for {use case 1}, {use case 2}, and {use case 3}.
```

### **Patch Release Template**
```
v{VERSION} - {Brief description}

Fixed issues and improvements:
• {Fix 1}
• {Fix 2}
• {Improvement 1}

This is a patch release that {benefit} without breaking changes.
```

---

## 🔍 Important Technical Details

### **App Type Handling**
- Always ensure both "HomGar" and "RainPoint" options are available
- Default existing users to "homgar" for backward compatibility
- Update brand detection in `coordinator.py` based on `app_type`
- Test both app flows with same credentials when possible

### **API Optimization**
- Use `multipleDeviceStatus` for efficiency
- Implement hybrid fallback strategy
- Handle rate limiting with appropriate delays
- Test with both appCode values (1 for HomGar, 2 for RainPoint)

### **Device Support**
- Add new device models to `const.py`
- Implement hex payload decoding in sensor classes
- Add raw payload sensors for debugging
- Create unsupported sensor detection

### **Multi-Account Support**
- Ensure each integration instance is independent
- Test with multiple accounts if possible
- Document entity naming patterns
- Handle API login conflicts properly

---

## ⚠️ Critical Reminders

### **API Login Conflict**
- **ALWAYS** document that API login logs out mobile app
- **ALWAYS** provide separate API account solution
- **ALWAYS** include step-by-step account creation guide
- **ALWAYS** add to troubleshooting section

### **Backward Compatibility**
- Default existing users to HomGar app type
- Never break existing configurations
- Test upgrade path from previous versions
- Document any required user actions

### **Documentation Standards**
- Use "HomGar/RainPoint" interchangeably
- Explain HomGar is app, RainPoint is hardware
- Provide clear setup instructions
- Include comprehensive troubleshooting

### **Code Quality**
- No external dependencies
- Native async implementation
- Proper error handling
- Comprehensive logging

---

## 📋 Post-Release Checklist

### **GitHub Release**
- [ ] Create release on GitHub using tag
- [ ] Use appropriate template for release notes
- [ ] Include installation instructions
- [ ] Link to documentation

### **Community Announcement**
- [ ] Post on Home Assistant Community Forum
- [ ] Share in relevant Discord channels
- [ ] Monitor for user feedback and issues
- [ ] Respond to questions and bug reports

### **Monitoring**
- [ ] Watch for new issues on GitHub
- [ ] Monitor for crash reports
- [ ] Check user feedback on forums
- [ ] Prepare for quick patch release if needed

---

## 🔄 Common Scenarios

### **Adding New Device Model**
1. Add model constants to `const.py`
2. Implement hex decoding in `sensor.py`
3. Update device compatibility table in README
4. Test with actual device if possible
5. Add to supported devices list

### **Updating API Calls**
1. Test new API endpoints thoroughly
2. Implement fallback for older endpoints
3. Update error handling
4. Document any breaking changes
5. Test with both app types

### **UI/UX Changes**
1. Update `strings.json` for new labels
2. Update README with screenshots if needed
3. Test configuration flow end-to-end
4. Ensure translation support
5. Update documentation

---

## 🎯 Quick Reference Commands

### **Version Bump & Release**
```bash
# Update manifest version
# Commit changes
# Create tag
# Push to remote
```

### **Emergency Patch**
```bash
git add .
git commit -m "fix: v{VERSION} - {Critical fix}"
git tag -a v{VERSION} -m "v{VERSION} - Critical fix"
git push origin main && git push origin v{VERSION}
```

### **Rollback (if needed)**
```bash
git reset --hard HEAD~1
git push --force origin main
# Delete problematic tag
git tag -d v{VERSION}
git push --delete origin v{VERSION}
```

---

## 📞 Support and Troubleshooting

### **Common User Issues**
- API login conflicts → Separate account solution
- No devices found → Check app type selection
- Entities not updating → Verify credentials and app selection
- Multiple account confusion → Check integration instance

### **Debugging Steps**
1. Enable debug logging
2. Check raw payload sensors
3. Verify app type selection
4. Test API endpoints manually
5. Check for rate limiting

---

**Remember**: This integration is used by real users. Always prioritize stability, backward compatibility, and clear documentation! 🎯
